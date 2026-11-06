"""Fetch Google autocomplete keyword suggestions for an article seed."""

import requests

from .errors import NetworkError, ValidationError

SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (compatible; TAAS/1.0)"


def suggest_keywords(seed, http=requests):
    query = " ".join((seed or "").split())
    if not query:
        raise ValidationError("Enter a seed keyword first.")

    try:
        response = http.get(
            SUGGEST_URL,
            params={"client": "firefox", "q": query},
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=TIMEOUT,
        )
    except (requests.ConnectionError, requests.Timeout):
        raise NetworkError("Google keyword suggestions could not be reached. Check the internet connection.")
    except requests.RequestException:
        raise NetworkError("Google keyword suggestions could not be retrieved.")

    if response.status_code >= 400:
        raise NetworkError(f"Google keyword suggestions returned HTTP {response.status_code}.")

    try:
        data = response.json()
    except ValueError:
        raise NetworkError("Google returned unreadable keyword suggestions.")

    if not isinstance(data, list) or len(data) < 2 or not isinstance(data[1], list):
        raise NetworkError("Google returned an unexpected keyword-suggestions response.")

    suggestions = []
    seen = set()
    for item in data[1]:
        if not isinstance(item, str):
            continue
        keyword = " ".join(item.split())
        key = keyword.casefold()
        if keyword and key not in seen:
            suggestions.append(keyword)
            seen.add(key)
    if not suggestions:
        raise NetworkError("Google did not return any keyword suggestions for that phrase.")
    return suggestions
