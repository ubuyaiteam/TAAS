"""OpenAI client: send a chat prompt, get text back."""

import requests

from .errors import ConfigError, NetworkError, OpenAIError

API_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIClient:
    """Talks to the OpenAI Chat Completions API with the user's own key."""

    def __init__(self, api_key, model, http=requests, timeout=90):
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self._http = http
        self._timeout = timeout

    def generate(self, prompt, system="", temperature=None, json_mode=False):
        if not self.api_key:
            raise ConfigError("The OpenAI API key is missing. Enter it in Setup.")
        if not self.model:
            raise ConfigError("The OpenAI model name is missing. Set OPENAI_MODEL in Setup.")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body = {"model": self.model, "messages": messages}
        if temperature is not None:
            body["temperature"] = temperature
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        try:
            resp = self._http.post(
                API_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=body,
                timeout=self._timeout,
            )
        except (requests.ConnectionError, requests.Timeout):
            raise NetworkError("Could not reach OpenAI. Check the internet connection.")

        data = self._json(resp)
        if resp.status_code != 200:
            raise self._error_for(resp.status_code, data)
        choices = data.get("choices") or []
        text = ((choices[0].get("message") or {}).get("content") or "").strip() if choices else ""
        if not text:
            raise OpenAIError("OpenAI returned no text. Try again.")
        return text

    @staticmethod
    def _json(resp):
        try:
            data = resp.json()
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def _error_for(self, status, data):
        error = data.get("error") or {}
        message = error.get("message", "")
        if status in (401, 403):
            return ConfigError("OpenAI did not accept the API key. Check it in Setup.")
        if status == 404:
            return ConfigError(f"The OpenAI model '{self.model}' was not found. Check the model name in Setup.")
        if status == 429:
            return OpenAIError("The OpenAI limit was reached. Wait a little and try again.")
        if status >= 500:
            return OpenAIError("OpenAI is not available right now. Try again later.")
        return OpenAIError(f"OpenAI rejected the request (HTTP {status}): {message}".strip())
