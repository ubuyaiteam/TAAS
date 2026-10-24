"""End-to-end tests: the REAL code layers (sign-in tokens, page reader, Gemini client, Blogger client)
run against one fake internet. Only the network is faked."""

import json  # read and write JSON
import os  # environment variables
import random  # fixed random numbers for tests
import tempfile  # temporary folders
import unittest  # test tools
from pathlib import Path  # file paths

import requests  # web request errors

from taas import auth, config, workflow  # the code being tested
from taas.blogger import BloggerClient  # real Blogger client
from taas.errors import AuthRequiredError, BloggerError, ConfigError, NetworkError  # our error types
from taas.gemini import GeminiClient  # real Gemini client
from taas.pagereader import read_page  # real page reader

from tests.helpers import KEYWORDS, reply  # test helpers
from tests.test_gemini_pagereader import Resp  # a fake web answer

SHOP = "https://shop-one.example.com/desks"
GUIDE = "https://www.second-site.co.uk/guides/chairs"
PAGE = ("<html lang='en-IN'><head><title>{t}</title><meta name='description' content='Desks and chairs for homes.'>"
        "</head><body><main><h1>{t}</h1><p>" + "Good desks and chairs for work. " * 20 + "</p></main></body></html>")
DETECT = json.dumps({"brand": "Example Brand", "category": "office furniture", "country": "India"})
ANCHORS = json.dumps({"anchors": ["great deals", "buying guide"]})


def gemini_ok(text):
    return Resp(200, {"candidates": [{"content": {"parts": [{"text": text}]}}]})


# One fake internet: pages, Google token page, Gemini and Blogger
class FakeInternet:
    def __init__(self):
        self.pages = {SHOP: Resp(200, text=PAGE.format(t="Desks")), GUIDE: Resp(200, text=PAGE.format(t="Chair guide"))}
        self.gemini_answers = []  # scripted Gemini answers (text, or a Resp for an error)
        self.token_answer = {"access_token": "fresh-token", "expires_in": 3600}
        self.token_status = 200
        self.blogger_error = None  # a Resp or an exception for the post call
        self.log = []  # (kind, url, details)

    def get(self, url, headers=None, timeout=None):
        self.log.append(("page", url, headers))
        item = self.pages[url]
        if isinstance(item, Exception):
            raise item
        return item

    def post(self, url, headers=None, json=None, data=None, timeout=None):
        if "oauth2.googleapis.com" in url:
            self.log.append(("token", url, data))
            return Resp(self.token_status, self.token_answer)
        self.log.append(("gemini", url, {"headers": headers, "json": json}))
        item = self.gemini_answers.pop(0)
        return item if isinstance(item, Resp) else gemini_ok(item)

    def request(self, method, url, headers=None, timeout=None, params=None, json=None):
        self.log.append(("blogger", url, {"method": method, "headers": headers, "params": params, "json": json}))
        if url.endswith("/users/self/blogs"):
            return Resp(200, {"items": [{"id": "111", "name": "My blog", "url": "https://my.blogspot.com/"}]})
        if self.blogger_error:
            if isinstance(self.blogger_error, Exception):
                raise self.blogger_error
            return self.blogger_error
        return Resp(200, {"id": "p9", "url": "https://my.blogspot.com/p.html",
                          "status": "DRAFT" if params["isDraft"] == "true" else "LIVE", "content": json["content"]})

    def calls(self, kind):
        return [c for c in self.log if c[0] == kind]


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        old = os.environ.get("TAAS_HOME")
        os.environ["TAAS_HOME"] = str(self.home)
        self.addCleanup(lambda: os.environ.__setitem__("TAAS_HOME", old) if old else os.environ.pop("TAAS_HOME", None))
        (self.home / "client_secret.json").write_text(json.dumps({"installed": {"client_id": "cid", "client_secret": "s"}}))

        self.net = FakeInternet()
        self.clock = 1_000_000.0
        client = auth.load_client_config(self.home / "client_secret.json")
        self.wf = workflow.Workflow(
            gemini_factory=lambda s: GeminiClient(s.gemini_api_key, s.gemini_model, http=self.net),
            blogger_factory=lambda: BloggerClient(
                auth.GoogleAuth(client, self.wf.store, http=self.net, now=lambda: self.clock).access_token, http=self.net),
            reader=lambda url, http: read_page(url, self.net),
            now=lambda: self.clock, rng=random.Random(2),
        )
        self.wf.save_settings("MY-GEMINI-KEY", "test-model", "300", "400", "")
        self.wf.select_blog("111")
        # signed in earlier; the saved access token has already expired
        self.wf.store.save({"access_token": "old-token", "refresh_token": "r1", "expires_at": self.clock - 10})

    def run_to_draft(self):
        self.net.gemini_answers += [DETECT, DETECT, ANCHORS, reply(), reply()]
        analysis = self.wf.analyze([SHOP, GUIDE], "\n".join(KEYWORDS))
        return self.wf.generate(analysis, analysis.category, analysis.country, analysis.brands)

    def test_the_whole_flow_through_every_real_layer(self):
        draft = self.run_to_draft()
        self.assertTrue(draft.report.passed, draft.report.problems)

        # pages were fetched with our name, Gemini got the key in a header and the chosen model in the address
        self.assertEqual([c[1] for c in self.net.calls("page")], [SHOP, GUIDE])
        self.assertIn("TAAS", self.net.calls("page")[0][2]["User-Agent"])
        for _, url, details in self.net.calls("gemini"):
            self.assertTrue(url.endswith("/test-model:generateContent"))
            self.assertEqual(details["headers"]["x-goog-api-key"], "MY-GEMINI-KEY")
            self.assertNotIn("MY-GEMINI-KEY", url)
        self.assertEqual(len(self.net.calls("gemini")), 5)  # 2 detections, 1 anchors, article, humanize

        result = self.wf.post(draft, draft.title, draft.text, live=False, confirmed=True)
        self.assertEqual((result.status, result.live, result.url), ("DRAFT", False, "https://my.blogspot.com/p.html"))

        # the expired token was refreshed once, and Blogger got the fresh one
        self.assertEqual(len(self.net.calls("token")), 1)
        self.assertEqual(self.net.calls("token")[0][2]["grant_type"], "refresh_token")
        post_call = [c for c in self.net.calls("blogger") if "/posts/" in c[1]][0]
        self.assertEqual(post_call[2]["headers"]["Authorization"], "Bearer fresh-token")
        self.assertEqual(post_call[2]["params"], {"isDraft": "true"})
        self.assertTrue(post_call[1].endswith("/blogs/111/posts/"))

        # the posted article has exactly the two links, to the exact addresses
        sent = post_call[2]["json"]
        self.assertEqual(sent["content"].count("<a "), 2)
        self.assertIn(f'<a href="{SHOP}">great deals</a>', sent["content"])
        self.assertIn(f'<a href="{GUIDE}">buying guide</a>', sent["content"])
        self.assertNotIn("Example Brand", sent["content"])
        self.assertNotIn("example.com", sent["content"].replace(SHOP, "").replace(GUIDE, ""))

    def test_live_post_and_the_repeat_warning_on_the_next_run(self):
        draft = self.run_to_draft()
        self.wf.post(draft, draft.title, draft.text, live=True, confirmed=True)
        post_call = [c for c in self.net.calls("blogger") if "/posts/" in c[1]][0]
        self.assertEqual(post_call[2]["params"], {"isDraft": "false"})
        self.clock += 3600
        draft2 = self.run_to_draft()
        warnings = self.wf.warnings_before_post(draft2, draft2.title, draft2.text)
        self.assertTrue(any("already used" in w for w in warnings))

    def test_revoked_google_access_asks_to_sign_in_again(self):
        draft = self.run_to_draft()
        self.net.token_status, self.net.token_answer = 400, {"error": "invalid_grant"}
        with self.assertRaises(AuthRequiredError):
            self.wf.post(draft, draft.title, draft.text, live=False, confirmed=True)
        self.assertFalse(self.wf.is_signed_in())
        self.assertEqual([c for c in self.net.calls("blogger") if "/posts/" in c[1]], [])

    def test_unknown_gemini_model_is_explained(self):
        self.net.gemini_answers += [Resp(404, {"error": {"message": "models/test-model is not found"}})]
        with self.assertRaises(ConfigError) as ctx:
            self.wf.analyze([SHOP, GUIDE], "\n".join(KEYWORDS))
        self.assertIn("test-model", str(ctx.exception))
        self.assertIn("GEMINI_MODEL", str(ctx.exception))

    def test_a_blocked_page_means_typing_the_details_by_hand(self):
        self.net.pages[SHOP] = Resp(403)
        self.net.gemini_answers += [DETECT, ANCHORS, reply(), reply()]  # only the readable page is sent to Gemini
        analysis = self.wf.analyze([SHOP, GUIDE], "\n".join(KEYWORDS))
        self.assertIn("by hand", analysis.analyses[0].detection.error)
        draft = self.wf.generate(analysis, "office furniture", "India", ["Typed Brand"])
        self.assertTrue(draft.report.passed, draft.report.problems)
        self.assertIn("Typed Brand", draft.forbidden)

    def test_blogger_quota_error_is_shown_and_not_counted(self):
        draft = self.run_to_draft()
        self.net.blogger_error = Resp(403, {"error": {"message": "Quota exceeded"}})
        with self.assertRaises(BloggerError) as ctx:
            self.wf.post(draft, draft.title, draft.text, live=True, confirmed=True)
        self.assertIn("Quota exceeded", str(ctx.exception))
        self.assertEqual(self.wf.log.live_posts_last_day("111", self.clock), 0)

    def test_internet_down_while_posting(self):
        draft = self.run_to_draft()
        self.net.blogger_error = requests.ConnectionError("down")
        with self.assertRaises(NetworkError):
            self.wf.post(draft, draft.title, draft.text, live=False, confirmed=True)

    def test_no_secret_is_written_to_the_post_log_or_the_env(self):
        draft = self.run_to_draft()
        self.wf.post(draft, draft.title, draft.text, live=False, confirmed=True)
        env = (self.home / ".env").read_text()
        self.assertIn("MY-GEMINI-KEY", env)  # the Gemini key lives only here
        self.assertNotIn("r1", env.replace("TAAS", ""))  # the Google refresh token never goes in .env
        log = (self.home / "post_log.json").read_text()
        for secret in ("MY-GEMINI-KEY", "fresh-token", "Example Brand", draft.title):
            self.assertNotIn(secret, log)


if __name__ == "__main__":
    unittest.main()
