import unittest

import requests

from taas.errors import ConfigError, NetworkError, OpenAIError
from taas.openai import API_URL, OpenAIClient


class Response:
    def __init__(self, status=200, body=None, bad_json=False):
        self.status_code = status
        self.body = body or {}
        self.bad_json = bad_json

    def json(self):
        if self.bad_json:
            raise ValueError("invalid json")
        return self.body


class FakeHttp:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class OpenAIClientTests(unittest.TestCase):
    def client(self, response, key="K", model="gpt-test"):
        http = FakeHttp(response)
        return OpenAIClient(key, model, http=http), http

    def test_success_and_request_shape(self):
        client, http = self.client(Response(body={"choices": [{"message": {"content": " Hi "}}]}))
        self.assertEqual(client.generate("Q", system="S", temperature=0.2, json_mode=True), "Hi")
        url, request = http.calls[0]
        self.assertEqual(url, API_URL)
        self.assertEqual(request["headers"]["Authorization"], "Bearer K")
        self.assertNotIn("K", url)
        self.assertEqual(request["json"]["model"], "gpt-test")
        self.assertEqual(request["json"]["messages"], [
            {"role": "system", "content": "S"}, {"role": "user", "content": "Q"},
        ])
        self.assertEqual(request["json"]["temperature"], 0.2)
        self.assertEqual(request["json"]["response_format"], {"type": "json_object"})

    def test_missing_credentials(self):
        with self.assertRaises(ConfigError):
            self.client(Response(), key="")[0].generate("Q")
        with self.assertRaises(ConfigError):
            self.client(Response(), model="")[0].generate("Q")

    def test_api_errors(self):
        cases = [
            (401, ConfigError),
            (403, ConfigError),
            (404, ConfigError),
            (429, OpenAIError),
            (503, OpenAIError),
            (400, OpenAIError),
        ]
        for status, expected in cases:
            with self.subTest(status=status), self.assertRaises(expected):
                self.client(Response(status, {"error": {"message": "rejected"}}))[0].generate("Q")

    def test_empty_reply_and_network_errors(self):
        with self.assertRaises(OpenAIError):
            self.client(Response(body={"choices": []}))[0].generate("Q")
        for error in (requests.ConnectionError("offline"), requests.Timeout("timeout")):
            with self.subTest(error=error), self.assertRaises(NetworkError):
                self.client(error)[0].generate("Q")


if __name__ == "__main__":
    unittest.main()
