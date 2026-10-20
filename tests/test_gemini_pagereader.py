import json  # read JSON
import unittest  # test tools

import requests  # web request errors

from taas import gemini, pagereader  # the code being tested
from taas.errors import ConfigError, GeminiError, NetworkError, PageReadError  # our error types


# Fake web answer
class Resp:
    def __init__(self, status=200, body=None, text="", headers=None, bad_json=False):
        self.status_code = status
        self._body = body if body is not None else {}
        self.text = text
        self.headers = headers if headers is not None else {"Content-Type": "text/html; charset=utf-8"}
        self._bad = bad_json

    def json(self):
        if self._bad:
            raise ValueError("no json")
        return self._body


# Fake web: keeps calls, returns the prepared answers
class FakeWeb:
    def __init__(self, *items):
        self.items = list(items)
        self.calls = []

    def _next(self, url, **kw):
        self.calls.append((url, kw))
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def post(self, url, **kw):
        return self._next(url, **kw)

    def get(self, url, **kw):
        return self._next(url, **kw)


def ok(text="hello"):
    return Resp(200, {"candidates": [{"content": {"parts": [{"text": text}]}}]})


# Tests for the Gemini client
class GeminiClientTests(unittest.TestCase):
    def client(self, *items, key="K", model="gemini-test"):
        web = FakeWeb(*items)
        return gemini.GeminiClient(key, model, http=web), web

    def test_success_and_request_shape(self):
        c, web = self.client(ok("Hi there"))
        self.assertEqual(c.generate("Q", system="S", temperature=0.5, json_mode=True), "Hi there")
        url, kw = web.calls[0]
        self.assertTrue(url.endswith("/gemini-test:generateContent"))
        self.assertEqual(kw["headers"]["x-goog-api-key"], "K")
        self.assertNotIn("K", url)  # the key never goes in the link
        self.assertEqual(kw["json"]["systemInstruction"]["parts"][0]["text"], "S")
        self.assertEqual(kw["json"]["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(kw["json"]["generationConfig"]["temperature"], 0.5)

    def test_models_prefix_is_removed(self):
        c, web = self.client(ok(), model="models/gemini-x")
        c.generate("Q")
        self.assertIn("/models/gemini-x:generateContent", web.calls[0][0])

    def test_missing_key_or_model(self):
        with self.assertRaises(ConfigError):
            self.client(key="")[0].generate("Q")
        with self.assertRaises(ConfigError):
            self.client(model="")[0].generate("Q")

    def test_error_codes(self):
        cases = [
            (Resp(400, {"error": {"message": "API key not valid"}}), ConfigError),
            (Resp(403, {"error": {"message": "denied"}}), ConfigError),
            (Resp(404, {"error": {"message": "not found"}}), ConfigError),
            (Resp(429, {}), GeminiError),
            (Resp(503, {}), GeminiError),
            (Resp(400, {"error": {"message": "bad field"}}), GeminiError),
            (Resp(500, bad_json=True), GeminiError),
        ]
        for resp, expected in cases:
            with self.assertRaises(expected):
                self.client(resp)[0].generate("Q")

    def test_model_not_found_names_the_model(self):
        with self.assertRaises(ConfigError) as ctx:
            self.client(Resp(404, {}), model="gemini-9")[0].generate("Q")
        self.assertIn("gemini-9", str(ctx.exception))

    def test_blocked_and_empty_answers(self):
        with self.assertRaises(GeminiError):
            self.client(Resp(200, {"promptFeedback": {"blockReason": "SAFETY"}}))[0].generate("Q")
        with self.assertRaises(GeminiError):
            self.client(Resp(200, {"candidates": []}))[0].generate("Q")

    def test_network_down(self):
        with self.assertRaises(NetworkError):
            self.client(requests.ConnectionError("x"))[0].generate("Q")
        with self.assertRaises(NetworkError):
            self.client(requests.Timeout("x"))[0].generate("Q")


# Tests for reading Gemini's JSON text
class ParseJsonTests(unittest.TestCase):
    def test_plain_and_fenced(self):
        self.assertEqual(gemini.parse_json_reply('{"a": 1}'), {"a": 1})
        self.assertEqual(gemini.parse_json_reply('```json\n{"a": 1}\n```'), {"a": 1})

    def test_text_around_json(self):
        self.assertEqual(gemini.parse_json_reply('Here: {"a": 1} done'), {"a": 1})

    def test_not_json(self):
        for bad in ("hello", "[1, 2]", ""):
            with self.assertRaises(GeminiError):
                gemini.parse_json_reply(bad)


PAGE = """<html lang="en-IN"><head><title>Desks | Acme</title>
<meta name="description" content="Standing desks for homes.">
<meta property="og:site_name" content="Acme Store"><meta property="og:locale" content="en_IN">
<script>var secret = 1;</script></head>
<body><nav>MENU LINKS</nav><main><h1>Standing desks</h1>
<p>Our desks start at \u20b9 9,999 and ship across India. """ + ("Good desks for work. " * 20) + """</p></main>
<footer>FOOTER TEXT</footer></body></html>"""


# Tests for reading pages
class PageReaderTests(unittest.TestCase):
    def test_extract_page(self):
        page = pagereader.extract_page(PAGE, "https://www.acme.in/desks")
        self.assertEqual(page.title, "Desks | Acme")
        self.assertEqual(page.description, "Standing desks for homes.")
        self.assertEqual(page.site_name, "Acme Store")
        self.assertEqual((page.lang, page.locale, page.host), ("en-IN", "en_IN", "www.acme.in"))
        self.assertIn("\u20b9", page.currencies)
        self.assertIn("Standing desks", page.text)
        for junk in ("MENU LINKS", "FOOTER TEXT", "secret"):
            self.assertNotIn(junk, page.text)
        self.assertFalse(page.thin)

    def test_thin_page(self):
        page = pagereader.extract_page("<html><body><div id='app'></div></body></html>", "https://a.com")
        self.assertTrue(page.thin)

    def test_text_is_cut(self):
        big = "<html><body><p>" + "word " * 5000 + "</p></body></html>"
        self.assertLessEqual(len(pagereader.extract_page(big, "https://a.com").text), pagereader.MAX_TEXT_CHARS)

    def test_fetch_ok(self):
        web = FakeWeb(Resp(200, text="<html>ok</html>"))
        self.assertEqual(pagereader.fetch_page("https://a.com", web), "<html>ok</html>")
        self.assertIn("User-Agent", web.calls[0][1]["headers"])

    def test_fetch_problems(self):
        cases = [Resp(403), Resp(404), Resp(500), Resp(200, headers={"Content-Type": "application/pdf"}),
                 requests.exceptions.SSLError("x"), requests.ConnectionError("x"), requests.Timeout("x")]
        for item in cases:
            with self.assertRaises(PageReadError):
                pagereader.fetch_page("https://a.com", FakeWeb(item))


if __name__ == "__main__":
    unittest.main()
