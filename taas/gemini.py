"""Gemini client: send a prompt, get text back."""

import json  # read JSON answers
import re  # find patterns in text

import requests  # send web requests

from .errors import ConfigError, GeminiError, NetworkError  # our error types

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"  # Gemini web address


class GeminiClient:
    """Talks to the Gemini API with the user's own key."""

    def __init__(self, api_key, model, http=requests, timeout=90):
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip().removeprefix("models/")
        self._http = http
        self._timeout = timeout

    # Send one prompt, return Gemini's text
    def generate(self, prompt, system="", temperature=None, json_mode=False):
        if not self.api_key:
            raise ConfigError("The Gemini API key is missing. Add GEMINI_API_KEY to the .env file.")
        if not self.model:
            raise ConfigError("The Gemini model name is missing. Set GEMINI_MODEL in the .env file.")

        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        config = {}
        if temperature is not None:
            config["temperature"] = temperature
        if json_mode:
            config["responseMimeType"] = "application/json"  # ask for a JSON answer
        if config:
            body["generationConfig"] = config

        try:
            resp = self._http.post(
                f"{API_ROOT}/{self.model}:generateContent",
                headers={"x-goog-api-key": self.api_key},  # the key goes in a header, not the link
                json=body,
                timeout=self._timeout,
            )
        except (requests.ConnectionError, requests.Timeout):
            raise NetworkError("Could not reach Gemini. Check the internet connection.")

        data = self._json(resp)
        if resp.status_code != 200:
            raise self._error_for(resp.status_code, data)
        return self._text_from(data)

    # Read the answer as JSON (empty if it is not JSON)
    @staticmethod
    def _json(resp):
        try:
            data = resp.json()
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    # Turn an error answer into the right error
    def _error_for(self, status, data):
        message = (data.get("error") or {}).get("message", "")
        if status in (400, 401, 403) and ("api key" in message.lower() or status in (401, 403)):
            return ConfigError("Gemini did not accept the API key. Check GEMINI_API_KEY in the .env file.")
        if status == 404:
            return ConfigError(
                f"The Gemini model '{self.model}' was not found. Check GEMINI_MODEL in the .env file."
            )
        if status == 429:
            return GeminiError("The Gemini limit was reached. Wait a little and try again.")
        if status >= 500:
            return GeminiError("Gemini is not available right now. Try again later.")
        return GeminiError(f"Gemini rejected the request (HTTP {status}): {message}".strip())

    # Pick the text out of Gemini's answer
    @staticmethod
    def _text_from(data):
        block = (data.get("promptFeedback") or {}).get("blockReason")
        if block:
            raise GeminiError(f"Gemini blocked this request ({block}).")
        candidates = data.get("candidates") or []
        parts = ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            raise GeminiError("Gemini returned no text. Try again.")
        return text


# Turn Gemini's text into a JSON object (removes ``` fences)
def parse_json_reply(text):
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    try:
        data = json.loads(cleaned)
    except ValueError:
        # last try: take everything from the first { to the last }
        start, end = cleaned.find("{"), cleaned.rfind("}")
        try:
            data = json.loads(cleaned[start:end + 1]) if 0 <= start < end else None
        except ValueError:
            data = None
    if not isinstance(data, dict):
        raise GeminiError("Gemini did not return a valid answer. Try again.")
    return data
