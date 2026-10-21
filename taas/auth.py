"""Google sign-in for Blogger. Only tokens are saved. No password is stored."""

from __future__ import annotations  # allow newer type hints

import base64  # turn bytes into web-safe text
import hashlib  # make SHA-256 hashes
import json  # read and write JSON files
import os  # system and file-permission tools
import secrets  # make random values
import time  # clock, for token expiry
import webbrowser  # open the browser
from dataclasses import dataclass  # simple data classes
from http.server import BaseHTTPRequestHandler, HTTPServer  # small local web server
from pathlib import Path  # file paths
from typing import Callable, Optional  # type hints
from urllib.parse import parse_qs, urlencode, urlparse  # read and build web links

import requests  # send web requests

from .errors import AuthRequiredError, ConfigError, NetworkError  # our error types

BLOGGER_SCOPE = "https://www.googleapis.com/auth/blogger"  # permission we ask Google for: use Blogger
DEFAULT_AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"  # Google's sign-in page
DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"  # Google's token page
EXPIRY_MARGIN_SECONDS = 60  # refresh the token 60 s before it ends


# Google client details
@dataclass
class ClientConfig:
    client_id: str  # from the Google client file
    client_secret: str  # from the Google client file
    auth_uri: str = DEFAULT_AUTH_URI  # Google's sign-in page
    token_uri: str = DEFAULT_TOKEN_URI  # Google's token page


def load_client_config(path: Path) -> ClientConfig:
    """Read the client file from Google Cloud."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(
            f"Google client file not found: {path}. "
            "Follow GOOGLE_SETUP.md to create it."
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ConfigError(f"Google client file is not valid JSON: {path}")

    # Desktop-app clients keep their details under 'installed'
    block = data.get("installed")
    if not isinstance(block, dict):
        raise ConfigError(
            "The Google client file must be an OAuth client of type 'Desktop app'."
        )
    client_id = block.get("client_id")
    client_secret = block.get("client_secret")
    if not client_id or not client_secret:
        raise ConfigError("The Google client file has no client_id or client_secret.")
    return ClientConfig(
        client_id=client_id,
        client_secret=client_secret,
        auth_uri=block.get("auth_uri") or DEFAULT_AUTH_URI,
        token_uri=block.get("token_uri") or DEFAULT_TOKEN_URI,
    )


# ---------------- Sign-in link ----------------

# Make bytes safe for a web link
def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def make_pkce() -> tuple[str, str]:
    """Make the code pair that protects the sign-in."""
    # random secret, kept on this PC
    verifier = _b64url(os.urandom(64))
    # its hash, which is sent to Google
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


# Build the Google sign-in link
def build_auth_url(
    client: ClientConfig, redirect_uri: str, state: str, code_challenge: str
) -> str:
    params = {
        "client_id": client.client_id,
        "redirect_uri": redirect_uri,
        # ask for a one-time code
        "response_type": "code",
        "scope": BLOGGER_SCOPE,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",  # keeps the user signed in
        "prompt": "select_account consent",  # user picks the account
    }
    return f"{client.auth_uri}?{urlencode(params)}"


# ---------------- Saved tokens ----------------

# Saved tokens
class TokenStore:
    """Saves tokens in a local file."""

    def __init__(self, path: Path):
        self.path = Path(path)

    # Read saved tokens
    def load(self) -> Optional[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    # Save tokens
    def save(self, token: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(token), encoding="utf-8")
        try:
            os.chmod(self.path, 0o600)  # lock the file (weak on Windows)
        except OSError:
            pass

    # Delete saved tokens
    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    # Is a user signed in?
    def is_signed_in(self) -> bool:
        token = self.load()
        return bool(token and token.get("refresh_token"))


# ---------------- Page that gets Google's reply ----------------

# Receives Google's reply
class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/":
            self.send_response(404)
            self.end_headers()
            return
        # keep Google's reply for the sign-in step
        self.server.result = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        body = (
            "<html><body style='font-family:sans-serif'>"
            "<h3>Sign-in finished.</h3><p>You can close this tab and return to TAAS.</p>"
            "</body></html>"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # no console messages
        pass


# Wait for Google's reply or time out
def _wait_for_callback(server: HTTPServer, timeout: float) -> Optional[dict]:
    # check for a reply every half second
    server.timeout = 0.5
    deadline = time.monotonic() + timeout
    while server.result is None and time.monotonic() < deadline:
        server.handle_request()
    return server.result


# ---------------- Ask Google for tokens ----------------

# Send a request to Google's token page
def _token_request(client: ClientConfig, data: dict, http=requests) -> dict:
    # add our client details to every request
    payload = dict(data, client_id=client.client_id, client_secret=client.client_secret)
    try:
        # send the request, wait up to 30 seconds
        resp = http.post(client.token_uri, data=payload, timeout=30)
    except (requests.ConnectionError, requests.Timeout):
        raise NetworkError("Could not reach Google. Check the internet connection.")

    try:
        body = resp.json()
    except ValueError:
        body = {}

    # success: Google sent a token
    if resp.status_code == 200 and "access_token" in body:
        return body

    error = body.get("error", "")
    # the user's access ended or was removed
    if error == "invalid_grant":
        raise AuthRequiredError(
            "Google access expired or was revoked. Please sign in again."
        )
    # our client file is wrong
    if error == "invalid_client":
        raise ConfigError(
            "Google rejected the client ID or secret. Check client_secret.json."
        )
    detail = body.get("error_description") or error or f"HTTP {resp.status_code}"
    raise AuthRequiredError(f"Google sign-in failed: {detail}")


# Add the expiry time to the tokens
def _with_expiry(body: dict, previous: Optional[dict], now: float) -> dict:
    token = {
        "access_token": body["access_token"],
        # Google sends a refresh token only the first time, so keep the old one
        "refresh_token": body.get("refresh_token")
        or (previous or {}).get("refresh_token", ""),
        # time when the token stops working
        "expires_at": now + float(body.get("expires_in", 3600)),
        "scope": body.get("scope", BLOGGER_SCOPE),
        "token_type": body.get("token_type", "Bearer"),
    }
    return token


# ---------------- Sign in ----------------

# Main sign-in step
def sign_in(
    client: ClientConfig,
    store: TokenStore,
    open_browser: Callable[[str], object] = webbrowser.open,
    timeout: float = 180,
    http=requests,
    now: Callable[[], float] = time.time,
) -> dict:
    """Open the browser, sign in, save the tokens."""
    # port 0 = any free port; 127.0.0.1 = this PC only
    server = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    server.result = None
    # Google sends the user back to this address
    redirect_uri = f"http://127.0.0.1:{server.server_address[1]}"
    # random value to confirm the reply is ours
    state = secrets.token_urlsafe(24)
    verifier, challenge = make_pkce()
    url = build_auth_url(client, redirect_uri, state, challenge)

    try:
        # show Google's sign-in page
        open_browser(url)
        result = _wait_for_callback(server, timeout)
    finally:
        # always stop the local server
        server.server_close()

    if result is None:
        raise AuthRequiredError("Sign-in timed out. Please try again.")
    if result.get("error"):
        raise AuthRequiredError(
            f"Google sign-in was cancelled or refused ({result['error']})."
        )
    # wrong value: the reply is not ours
    if result.get("state") != state:
        raise AuthRequiredError("Sign-in could not be verified. Please try again.")
    code = result.get("code")
    if not code:
        raise AuthRequiredError("Google did not return a sign-in code.")

    # swap the one-time code for tokens
    body = _token_request(
        client,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
        http=http,
    )
    token = _with_expiry(body, None, now())
    # Google lets the user untick permissions; without Blogger in the list, posting would fail later
    granted = body.get("scope")
    if granted and BLOGGER_SCOPE not in granted.split():
        raise AuthRequiredError(
            "Google did not give TAAS permission to use Blogger. Sign in again and tick the Blogger "
            "box when Google asks."
        )
    # no refresh token means signing in again and again
    if not token["refresh_token"]:
        raise AuthRequiredError(
            "Google did not return a refresh token. Remove TAAS from your Google "
            "account's third-party access and sign in again."
        )
    # keep the tokens for next time
    store.save(token)
    return token


# ---------------- Get a valid token ----------------

# Gives tokens to the Blogger client
class GoogleAuth:
    """Gives a valid token. Refreshes it when old."""

    def __init__(
        self,
        client: ClientConfig,
        store: TokenStore,
        http=requests,
        now: Callable[[], float] = time.time,
    ):
        self.client = client
        self.store = store
        self.http = http
        self.now = now

    # Return a valid token
    def access_token(self) -> str:
        token = self.store.load()
        if not token or not token.get("refresh_token"):
            # nothing saved: the user must sign in
            raise AuthRequiredError("Please sign in with Google first.")

        # token still good: use it
        if token.get("expires_at", 0) - self.now() > EXPIRY_MARGIN_SECONDS:
            return token["access_token"]

        try:
            body = _token_request(
                self.client,
                # ask for a new token using the refresh token
                {"grant_type": "refresh_token", "refresh_token": token["refresh_token"]},
                http=self.http,
            )
        except AuthRequiredError:
            self.store.clear()  # access lost: sign in again
            raise
        # save the new token
        fresh = _with_expiry(body, token, self.now())
        self.store.save(fresh)
        return fresh["access_token"]
