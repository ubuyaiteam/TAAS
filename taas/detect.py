"""Phase 2: find brand, category and country for each web address."""

from collections import Counter  # count the most common value
from dataclasses import dataclass  # simple data classes
from typing import Optional  # type hints

import requests  # send web requests

from .errors import ConfigError, GeminiError, PageReadError  # our error types
from .gemini import parse_json_reply  # turn Gemini's text into JSON
from .pagereader import PageInfo, read_page  # read web pages


# What was found for one web address
@dataclass
class Detection:
    url: str  # the address
    brand: str = ""  # brand shown on the page
    category: str = ""  # product or service type
    country: str = ""  # country the business is in or serves
    error: str = ""  # why detection failed (empty = fine)
    note: str = ""  # what the page is about, typed by the user (used when the page cannot be read)
    thin: bool = False  # True when the page had very little text


# One address with its page and its detection
@dataclass
class UrlAnalysis:
    url: str
    page: Optional[PageInfo]  # None when the page could not be read
    detection: Detection


SYSTEM = (
    "You read facts from web page details. Use only the details given. "
    "If something is not clear, return an empty string for it. Never guess. "
    "Return only JSON."
)


# Build the question for Gemini
def build_prompt(page):
    hints = (
        f"Website name: {page.host}\n"
        f"Domain ending: {page.host.rsplit('.', 1)[-1]}\n"
        f"Page language code: {page.lang or 'none'}\n"
        f"Page locale: {page.locale or 'none'}\n"
        f"Money signs seen: {', '.join(page.currencies) or 'none'}\n"
    )
    return (
        "Page details:\n"
        f"Title: {page.title or 'none'}\n"
        f"Description: {page.description or 'none'}\n"
        f"Site name: {page.site_name or 'none'}\n"
        f"{hints}"
        f"Page text (start): {page.text or 'none'}\n\n"
        "Return JSON with exactly these keys:\n"
        '{"brand": "...", "category": "...", "country": "..."}\n'
        "brand = the business, store or brand name shown on the page.\n"
        "category = the product or service type, in 2 to 4 words.\n"
        "country = the country (English name) where the business is based or that it serves.\n"
        "Use an empty string when you cannot tell."
    )


# Read and detect one web address; problems are saved in the result
def analyze_url(url, gemini, http=requests, reader=read_page):
    try:
        page = reader(url, http)
    except PageReadError as error:
        return UrlAnalysis(url, None, Detection(url, error=f"{error} Type the details by hand."))

    # nothing readable at all: do not ask Gemini to guess
    if not (page.title or page.description or page.text):
        message = "The page has no readable text (it may need JavaScript). Type the details by hand."
        return UrlAnalysis(url, page, Detection(url, error=message, thin=True))

    try:
        data = parse_json_reply(gemini.generate(build_prompt(page), system=SYSTEM, json_mode=True))
    except ConfigError:
        raise  # a wrong key or model stops everything
    except GeminiError as error:
        return UrlAnalysis(url, page, Detection(url, error=f"{error} Type the details by hand.", thin=page.thin))

    def clean(key):
        value = data.get(key, "")
        return value.strip() if isinstance(value, str) else ""

    detection = Detection(url, clean("brand"), clean("category"), clean("country"), thin=page.thin)
    return UrlAnalysis(url, page, detection)


# Analyze all addresses (one failing address does not stop the others)
def analyze_urls(urls, gemini, http=requests, reader=read_page):
    return [analyze_url(u, gemini, http, reader) for u in urls]


# The most common non-empty value (first one wins a tie)
def _most_common(values):
    values = [v for v in values if v]
    if not values:
        return ""
    counts = Counter(v.lower() for v in values)
    best = max(counts.values())
    for v in values:
        if counts[v.lower()] == best:
            return v


# Suggest one category, one country and the list of brands for the article
def summarize(analyses):
    category = _most_common([a.detection.category for a in analyses])
    country = _most_common([a.detection.country for a in analyses])
    brands = [a.detection.brand for a in analyses if a.detection.brand]
    return category, country, brands
