"""Blogger client: list blogs and create posts."""

from __future__ import annotations  # allow newer type hints

from dataclasses import dataclass  # simple data classes
from typing import Callable, List  # type hints
from urllib.parse import quote  # read and build web links

import requests  # send web requests

from .errors import AuthRequiredError, BloggerError, NetworkError, ValidationError  # our error types

API_BASE = "https://www.googleapis.com/blogger/v3"  # start of every Blogger web address


# One blog
@dataclass
class Blog:
    id: str  # Blogger id
    name: str  # blog name
    url: str  # web address


# One post
@dataclass
class Post:
    id: str
    url: str
    status: str  # LIVE or DRAFT
    content: str = ""  # post HTML as Blogger saved it


# Talks to Blogger
class BloggerClient:
    def __init__(self, access_token: Callable[[], str], http=requests, timeout: int = 30):
        self._access_token = access_token
        self._http = http
        self._timeout = timeout

    # Send one request to Blogger
    def _request(self, method: str, path: str, **kwargs) -> dict:
        # prove who we are with the token
        headers = {"Authorization": f"Bearer {self._access_token()}"}
        try:
            resp = self._http.request(
                method, API_BASE + path, headers=headers, timeout=self._timeout, **kwargs
            )
        except (requests.ConnectionError, requests.Timeout):
            raise NetworkError("Could not reach Blogger. Check the internet connection.")

        # 401 = sign-in not accepted
        if resp.status_code == 401:
            raise AuthRequiredError("Blogger did not accept the sign-in. Please sign in again.")
        # any other error code from Blogger
        if resp.status_code >= 400:
            raise BloggerError(self._error_message(resp))
        try:
            return resp.json()
        except ValueError:
            raise BloggerError("Blogger returned an unreadable answer.")

    # Make a short error text
    @staticmethod
    def _error_message(resp) -> str:
        try:
            message = resp.json().get("error", {}).get("message")
        except ValueError:
            message = None
        base = f"Blogger rejected the request (HTTP {resp.status_code})"
        text = f"{base}: {message}" if message else f"{base}."
        lowered = (message or "").lower()
        if resp.status_code == 403 and "scope" in lowered:
            text += (" Google did not give TAAS permission to use Blogger. In Setup, sign in again "
                     "and tick the Blogger box on Google's screen.")
        elif resp.status_code == 403 and "permission" in lowered:
            text += (" The Google account you are signed in with is not allowed to post to this blog. "
                     "Sign in with the account that owns this blog or is an author of it "
                     "(Setup > Use another Google account), then choose the blog again.")
        return text

    # Get the user's blogs
    def list_blogs(self) -> List[Blog]:
        data = self._request("GET", "/users/self/blogs")
        return [
            # Blogger ids can be numbers, so keep them as text
            Blog(id=str(item["id"]), name=item.get("name", ""), url=item.get("url", ""))
            for item in data.get("items", [])
        ]

    # Create a post (draft or live)
    def create_post(self, blog_id: str, title: str, html: str, draft: bool = True) -> Post:
        # check the input before calling Blogger
        if not blog_id or not blog_id.strip():
            raise ValidationError("No Blogger blog is selected.")
        if not title or not title.strip():
            raise ValidationError("The post needs a title.")
        if not html or not html.strip():
            raise ValidationError("The post has no content.")

        # the post, the way Blogger expects it
        body = {"kind": "blogger#post", "title": title.strip(), "content": html}
        data = self._request(
            "POST",
            # quote() stops odd characters breaking the web address
            f"/blogs/{quote(blog_id.strip(), safe='')}/posts/",
            # true = save as draft, false = publish
            params={"isDraft": "true" if draft else "false"},
            json=body,
        )
        return Post(
            id=str(data.get("id", "")),
            url=data.get("url", ""),
            status=data.get("status", ""),
            content=data.get("content", ""),
        )
