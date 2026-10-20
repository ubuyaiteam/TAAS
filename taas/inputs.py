"""Checks for what the user types: web addresses and keywords."""

import re  # find patterns in text
from urllib.parse import urlparse  # read web addresses

from .errors import ValidationError  # our error types

MIN_URLS, MAX_URLS = 2, 3  # links allowed per article
MIN_KEYWORDS, MAX_KEYWORDS = 5, 10  # keywords allowed per article


# Clean one web address and check it
def normalize_url(raw):
    url = (raw or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or " " in url:
        raise ValidationError(
            f"Not a valid web address: '{raw}'. It must start with http:// or https://"
        )
    return url


# Check the list of web addresses (2-3, no repeats)
def validate_urls(raw_urls):
    urls = [normalize_url(u) for u in raw_urls if u and u.strip()]
    if not MIN_URLS <= len(urls) <= MAX_URLS:
        raise ValidationError(f"Enter {MIN_URLS} to {MAX_URLS} web addresses.")
    # same address with or without a last "/" counts as a repeat
    keys = [u.lower().rstrip("/") for u in urls]
    if len(set(keys)) != len(keys):
        raise ValidationError("The same web address is entered twice.")
    return urls


# Check the list of keywords (5-10, no repeats)
def validate_keywords(raw_keywords):
    # remove extra spaces inside each keyword
    keywords = [re.sub(r"\s+", " ", k).strip() for k in raw_keywords if k and k.strip()]
    if not MIN_KEYWORDS <= len(keywords) <= MAX_KEYWORDS:
        raise ValidationError(f"Enter {MIN_KEYWORDS} to {MAX_KEYWORDS} keywords.")
    lowered = [k.lower() for k in keywords]
    if len(set(lowered)) != len(lowered):
        raise ValidationError("The same keyword is entered twice.")
    return keywords
