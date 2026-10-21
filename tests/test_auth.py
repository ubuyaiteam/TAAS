import base64  # turn bytes into web-safe text
import hashlib  # make SHA-256 hashes
import json  # read and write JSON files
import tempfile  # temporary files and folders for tests
import threading  # run a task in the background
import unittest  # test tools
from pathlib import Path  # file paths
from urllib.parse import parse_qs, urlparse  # read and build web links

import requests  # send web requests

from taas import auth  # the code being used or tested
from taas.errors import AuthRequiredError, ConfigError, NetworkError  # our error types


# Fake web answer
class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {}

    def json(self):
        return self._body


# Fake Google
class FakeHttp:
    """Fake Google. Saves calls, returns set answers."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, data=None, timeout=None):
        self.calls.append((url, dict(data)))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


# A pretend Google client
CLIENT = auth.ClientConfig(client_id="cid", client_secret="csecret")


# A token answer like Google's
def good_token_body(refresh="r1", expires_in=3600):
    body = {"access_token": "a1", "expires_in": expires_in, "token_type": "Bearer"}
    if refresh:
        body["refresh_token"] = refresh
    return body


# Tests for the Google client file
class ClientFileTests(unittest.TestCase):
    def write(self, data):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(data, tmp)
        tmp.close()
        return Path(tmp.name)

    def test_valid_desktop_client(self):
        p = self.write({"installed": {"client_id": "i", "client_secret": "s"}})
        c = auth.load_client_config(p)
        self.assertEqual((c.client_id, c.client_secret), ("i", "s"))
        self.assertEqual(c.token_uri, auth.DEFAULT_TOKEN_URI)

    def test_web_client_is_rejected(self):
        p = self.write({"web": {"client_id": "i", "client_secret": "s"}})
        with self.assertRaises(ConfigError):
            auth.load_client_config(p)

    def test_missing_secret_is_rejected(self):
        p = self.write({"installed": {"client_id": "i"}})
        with self.assertRaises(ConfigError):
            auth.load_client_config(p)

    def test_missing_and_broken_files(self):
        with self.assertRaises(ConfigError):
            auth.load_client_config(Path("/nonexistent/client.json"))
        bad = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        bad.write("{not json")
        bad.close()
        with self.assertRaises(ConfigError):
            auth.load_client_config(Path(bad.name))


# Tests for the sign-in code and link
class PkceAndUrlTests(unittest.TestCase):
    def test_challenge_matches_verifier(self):
        verifier, challenge = auth.make_pkce()
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        self.assertEqual(challenge, expected)
        self.assertNotEqual(auth.make_pkce()[0], verifier)

    def test_auth_url_contents(self):
        url = auth.build_auth_url(CLIENT, "http://127.0.0.1:5555", "st", "ch")
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        self.assertEqual(q["client_id"], "cid")
        self.assertEqual(q["scope"], auth.BLOGGER_SCOPE)
        self.assertEqual(q["code_challenge_method"], "S256")
        self.assertEqual(q["access_type"], "offline")
        self.assertEqual(q["redirect_uri"], "http://127.0.0.1:5555")
        self.assertNotIn("client_secret", q)


# Tests for saved tokens
class TokenStoreTests(unittest.TestCase):
    def test_save_load_clear(self):
        with tempfile.TemporaryDirectory() as d:
            store = auth.TokenStore(Path(d) / "token.json")
            self.assertIsNone(store.load())
            self.assertFalse(store.is_signed_in())
            store.save({"access_token": "a", "refresh_token": "r"})
            self.assertEqual(store.load()["refresh_token"], "r")
            self.assertTrue(store.is_signed_in())
            store.clear()
            self.assertIsNone(store.load())
            store.clear()  # twice is fine

    def test_corrupt_file_reads_as_signed_out(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "token.json"
            p.write_text("garbage")
            self.assertIsNone(auth.TokenStore(p).load())


# Tests for the sign-in steps
class SignInTests(unittest.TestCase):
    """Real local page. Fake browser and fake Google."""

    def run_sign_in(self, make_callback_query, http, timeout=5):
        with tempfile.TemporaryDirectory() as d:
            store = auth.TokenStore(Path(d) / "token.json")

            def fake_browser(url):
                q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
                redirect = q["redirect_uri"]
                query = make_callback_query(q["state"])

                def hit():
                    requests.get(f"{redirect}/?{query}", timeout=5)

                threading.Thread(target=hit, daemon=True).start()

            try:
                token = auth.sign_in(
                    CLIENT, store, open_browser=fake_browser, timeout=timeout,
                    http=http, now=lambda: 1000.0,
                )
                return token, store.load()
            except Exception:
                self.assertIsNone(store.load())  # nothing saved
                raise

    def test_successful_sign_in_stores_tokens(self):
        http = FakeHttp(FakeResponse(200, good_token_body()))
        token, stored = self.run_sign_in(lambda st: f"code=abc&state={st}", http)
        self.assertEqual(stored["refresh_token"], "r1")
        self.assertEqual(stored["expires_at"], 1000.0 + 3600)
        url, data = http.calls[0]
        self.assertEqual(url, auth.DEFAULT_TOKEN_URI)
        self.assertEqual(data["grant_type"], "authorization_code")
        self.assertEqual(data["code"], "abc")
        self.assertIn("code_verifier", data)

    def test_wrong_state_is_rejected(self):
        http = FakeHttp()
        with self.assertRaises(AuthRequiredError):
            self.run_sign_in(lambda st: "code=abc&state=WRONG", http)
        self.assertEqual(http.calls, [])  # no request sent

    def test_user_cancelling_is_reported(self):
        http = FakeHttp()
        with self.assertRaises(AuthRequiredError) as ctx:
            self.run_sign_in(lambda st: f"error=access_denied&state={st}", http)
        self.assertIn("access_denied", str(ctx.exception))

    def test_timeout_when_browser_never_returns(self):
        with tempfile.TemporaryDirectory() as d:
            store = auth.TokenStore(Path(d) / "token.json")
            with self.assertRaises(AuthRequiredError):
                auth.sign_in(CLIENT, store, open_browser=lambda u: None,
                             timeout=1, http=FakeHttp())

    def test_unticked_blogger_permission_is_refused_and_nothing_is_saved(self):
        body = dict(good_token_body(), scope="openid email")  # Google granted something else
        http = FakeHttp(FakeResponse(200, body))
        with self.assertRaises(AuthRequiredError) as ctx:
            self.run_sign_in(lambda st: f"code=abc&state={st}", http)
        self.assertIn("tick the Blogger box", str(ctx.exception))

    def test_blogger_permission_present_is_accepted(self):
        body = dict(good_token_body(), scope=f"openid {auth.BLOGGER_SCOPE}")
        http = FakeHttp(FakeResponse(200, body))
        token, stored = self.run_sign_in(lambda st: f"code=abc&state={st}", http)
        self.assertIn(auth.BLOGGER_SCOPE, stored["scope"])

    def test_missing_refresh_token_is_an_error(self):
        http = FakeHttp(FakeResponse(200, good_token_body(refresh=None)))
        with self.assertRaises(AuthRequiredError):
            self.run_sign_in(lambda st: f"code=abc&state={st}", http)


# Tests for token refresh
class RefreshTests(unittest.TestCase):
    def make(self, token, http):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        store = auth.TokenStore(Path(d.name) / "token.json")
        if token:
            store.save(token)
        return auth.GoogleAuth(CLIENT, store, http=http, now=lambda: 5000.0), store

    def test_signed_out_requires_sign_in(self):
        ga, _ = self.make(None, FakeHttp())
        with self.assertRaises(AuthRequiredError):
            ga.access_token()

    def test_valid_token_is_reused_without_network(self):
        http = FakeHttp()
        ga, _ = self.make(
            {"access_token": "keep", "refresh_token": "r", "expires_at": 9000.0}, http)
        self.assertEqual(ga.access_token(), "keep")
        self.assertEqual(http.calls, [])

    def test_expired_token_is_refreshed_and_refresh_token_kept(self):
        http = FakeHttp(FakeResponse(200, good_token_body(refresh=None)))
        ga, store = self.make(
            {"access_token": "old", "refresh_token": "r-old", "expires_at": 4990.0}, http)
        self.assertEqual(ga.access_token(), "a1")
        self.assertEqual(http.calls[0][1]["grant_type"], "refresh_token")
        saved = store.load()
        self.assertEqual(saved["refresh_token"], "r-old")
        self.assertEqual(saved["expires_at"], 5000.0 + 3600)

    def test_token_about_to_expire_is_refreshed(self):
        http = FakeHttp(FakeResponse(200, good_token_body(refresh=None)))
        ga, _ = self.make(
            {"access_token": "old", "refresh_token": "r", "expires_at": 5030.0}, http)
        self.assertEqual(ga.access_token(), "a1")  # inside the 60 s limit

    def test_revoked_access_clears_token_and_asks_to_sign_in(self):
        http = FakeHttp(FakeResponse(400, {"error": "invalid_grant"}))
        ga, store = self.make(
            {"access_token": "old", "refresh_token": "r", "expires_at": 0}, http)
        with self.assertRaises(AuthRequiredError):
            ga.access_token()
        self.assertIsNone(store.load())

    def test_network_failure_keeps_token(self):
        http = FakeHttp(requests.ConnectionError("down"))
        ga, store = self.make(
            {"access_token": "old", "refresh_token": "r", "expires_at": 0}, http)
        with self.assertRaises(NetworkError):
            ga.access_token()
        self.assertIsNotNone(store.load())

    def test_invalid_client_is_a_config_error(self):
        http = FakeHttp(FakeResponse(401, {"error": "invalid_client"}))
        ga, _ = self.make(
            {"access_token": "old", "refresh_token": "r", "expires_at": 0}, http)
        with self.assertRaises(ConfigError):
            ga.access_token()


if __name__ == "__main__":
    unittest.main()
