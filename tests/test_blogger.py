import unittest  # test tools

import requests  # send web requests

from taas.blogger import API_BASE, BloggerClient  # the code being used or tested
from taas.errors import AuthRequiredError, BloggerError, NetworkError, ValidationError  # our error types


# Fake web answer
class FakeResponse:
    def __init__(self, status=200, body=None, bad_json=False):
        self.status_code = status
        self._body = body if body is not None else {}
        self._bad = bad_json

    def json(self):
        if self._bad:
            raise ValueError("no json")
        return self._body


# Fake Blogger web
class FakeHttp:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, headers=None, timeout=None, **kwargs):
        self.calls.append({"method": method, "url": url, "headers": headers, **kwargs})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


# Blogger client that uses the fake web
def client(*responses):
    http = FakeHttp(*responses)
    return BloggerClient(lambda: "tok", http=http), http


# Tests for the blog list
class ListBlogsTests(unittest.TestCase):
    def test_lists_blogs(self):
        c, http = client(FakeResponse(200, {"items": [
            {"id": 111, "name": "One", "url": "https://one.blogspot.com/"},
            {"id": "222", "name": "Two", "url": "https://two.blogspot.com/"},
        ]}))
        blogs = c.list_blogs()
        self.assertEqual([b.id for b in blogs], ["111", "222"])
        call = http.calls[0]
        self.assertEqual(call["url"], API_BASE + "/users/self/blogs")
        self.assertEqual(call["headers"]["Authorization"], "Bearer tok")

    def test_no_blogs_gives_empty_list(self):
        c, _ = client(FakeResponse(200, {}))
        self.assertEqual(c.list_blogs(), [])


# Tests for creating posts
class CreatePostTests(unittest.TestCase):
    def ok(self, status="LIVE"):
        return FakeResponse(200, {"id": "p1", "url": "https://x.blogspot.com/p.html",
                                  "status": status})

    def test_draft_post(self):
        c, http = client(self.ok("DRAFT"))
        post = c.create_post("123", " My title ", "<p>Hello</p>", draft=True)
        call = http.calls[0]
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["url"], API_BASE + "/blogs/123/posts/")
        self.assertEqual(call["params"], {"isDraft": "true"})
        self.assertEqual(call["json"]["title"], "My title")
        self.assertEqual(call["json"]["content"], "<p>Hello</p>")
        self.assertEqual(post.status, "DRAFT")
        self.assertEqual(post.id, "p1")

    def test_live_post(self):
        c, http = client(self.ok())
        c.create_post("123", "T", "<p>x</p>", draft=False)
        self.assertEqual(http.calls[0]["params"], {"isDraft": "false"})

    def test_blog_id_is_url_encoded(self):
        c, http = client(self.ok())
        c.create_post("12/3", "T", "<p>x</p>")
        self.assertIn("/blogs/12%2F3/posts/", http.calls[0]["url"])

    def test_validation_happens_before_any_request(self):
        c, http = client()
        for args in (("", "T", "<p>x</p>"), ("1", "  ", "<p>x</p>"), ("1", "T", " ")):
            with self.assertRaises(ValidationError):
                c.create_post(*args)
        self.assertEqual(http.calls, [])


# Tests for error cases
class ErrorTests(unittest.TestCase):
    def test_401_asks_to_sign_in(self):
        c, _ = client(FakeResponse(401, {}))
        with self.assertRaises(AuthRequiredError):
            c.list_blogs()

    def test_blogger_error_message_is_shown(self):
        c, _ = client(FakeResponse(403, {"error": {"message": "Quota exceeded"}}))
        with self.assertRaises(BloggerError) as ctx:
            c.create_post("1", "T", "<p>x</p>")
        self.assertIn("Quota exceeded", str(ctx.exception))
        self.assertIn("403", str(ctx.exception))

    def test_error_without_json_body(self):
        c, _ = client(FakeResponse(500, bad_json=True))
        with self.assertRaises(BloggerError):
            c.list_blogs()

    def test_network_down(self):
        c, _ = client(requests.ConnectionError("down"))
        with self.assertRaises(NetworkError):
            c.list_blogs()

    def test_timeout(self):
        c, _ = client(requests.Timeout("slow"))
        with self.assertRaises(NetworkError):
            c.list_blogs()

    def test_unreadable_success_answer(self):
        c, _ = client(FakeResponse(200, bad_json=True))
        with self.assertRaises(BloggerError):
            c.list_blogs()


if __name__ == "__main__":
    unittest.main()
