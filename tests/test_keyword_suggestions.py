import unittest

import requests

from taas.errors import NetworkError, ValidationError
from taas.keyword_suggestions import SUGGEST_URL, suggest_keywords


class Response:
    def __init__(self, data, status=200):
        self.data = data
        self.status_code = status

    def json(self):
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


class FakeHttp:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


class KeywordSuggestionTests(unittest.TestCase):
    def test_requests_google_suggestions_and_cleans_duplicates(self):
        http = FakeHttp(Response(["diwali sale", [
            "diwali sale offers", "  Diwali sale deals ", "diwali sale offers", None,
        ]]))

        result = suggest_keywords("  diwali   sale ", http=http)

        self.assertEqual(result, ["diwali sale offers", "Diwali sale deals"])
        url, request = http.calls[0]
        self.assertEqual(url, SUGGEST_URL)
        self.assertEqual(request["params"], {"client": "firefox", "q": "diwali sale"})
        self.assertEqual(request["timeout"], 15)

    def test_rejects_empty_seed(self):
        with self.assertRaises(ValidationError):
            suggest_keywords("  ", http=FakeHttp())

    def test_network_failure_is_user_readable(self):
        with self.assertRaises(NetworkError):
            suggest_keywords("diwali sale", http=FakeHttp(error=requests.Timeout()))

    def test_http_failure_is_reported(self):
        with self.assertRaisesRegex(NetworkError, "HTTP 429"):
            suggest_keywords("diwali sale", http=FakeHttp(Response({}, status=429)))

    def test_invalid_response_is_reported(self):
        with self.assertRaises(NetworkError):
            suggest_keywords("diwali sale", http=FakeHttp(Response({"suggestions": []})))

    def test_empty_suggestions_are_reported(self):
        with self.assertRaises(NetworkError):
            suggest_keywords("diwali sale", http=FakeHttp(Response(["diwali sale", []])))


if __name__ == "__main__":
    unittest.main()
