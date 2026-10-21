"""Phase 2: read a web page and pull out title, description and text."""

import re  # find patterns in text
from dataclasses import dataclass, field  # simple data classes
from typing import List  # type hints
from urllib.parse import urlparse  # read web addresses

import requests  # send web requests
from bs4 import BeautifulSoup  # read HTML

from .errors import PageReadError  # our error types

USER_AGENT = "Mozilla/5.0 (compatible; TAAS-reader/1.0)"  # how we introduce ourselves to websites
FETCH_TIMEOUT = 20  # seconds to wait for a page
MAX_PAGE_CHARS = 2_000_000  # ignore anything after this much HTML
MAX_TEXT_CHARS = 4000  # how much page text we keep
THIN_TEXT_CHARS = 200  # less text than this: page may need JavaScript
CURRENCY_SYMBOLS = ["\u20b9", "\u00a3", "\u20ac", "\u00a5", "$"]  # hints about the country
CURRENCY_CODES = ["USD", "INR", "GBP", "EUR", "AED", "SAR", "CAD", "AUD", "SGD", "JPY", "KWD", "QAR"]


# What we learned about one page
@dataclass
class PageInfo:
    url: str  # the address that was read
    host: str = ""  # website name, like www.example.com
    title: str = ""  # page title
    description: str = ""  # page description
    site_name: str = ""  # site name given by the page
    lang: str = ""  # page language code
    locale: str = ""  # page locale code
    currencies: List[str] = field(default_factory=list)  # money signs seen on the page
    text: str = ""  # readable text (cut short)
    thin: bool = False  # True when the page has very little text


# Download one page and return its HTML
def fetch_page(url, http=requests):
    try:
        resp = http.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
            timeout=FETCH_TIMEOUT,
        )
    except requests.exceptions.SSLError:
        raise PageReadError(f"The secure connection to {url} failed.")
    except (requests.ConnectionError, requests.Timeout):
        raise PageReadError(f"{url} could not be reached.")
    except requests.RequestException:
        raise PageReadError(f"{url} could not be read.")

    status = resp.status_code
    if status in (401, 403, 429):
        raise PageReadError(
            f"{url} does not allow automatic reading (HTTP {status}). "
            "If this is your own site, ask your web team to allow the reader named TAAS-reader."
        )
    if status in (404, 410):
        raise PageReadError(f"{url} was not found (HTTP {status}).")
    if status >= 400:
        raise PageReadError(f"{url} gave an error (HTTP {status}).")

    kind = (getattr(resp, "headers", None) or {}).get("Content-Type", "")
    if kind and "html" not in kind.lower():
        raise PageReadError(f"{url} is not a web page ({kind}).")
    return resp.text[:MAX_PAGE_CHARS]


# Pull the useful parts out of the HTML
def extract_page(html_text, url):
    soup = BeautifulSoup(html_text, "html.parser")

    # read one <meta> tag value
    def meta(key, value):
        tag = soup.find("meta", attrs={key: value})
        return (tag.get("content") or "").strip() if tag else ""

    title = meta("property", "og:title") or (soup.title.get_text(" ", strip=True) if soup.title else "")
    description = meta("name", "description") or meta("property", "og:description")
    lang = (soup.html.get("lang") or "").strip() if soup.html else ""

    # remove parts that are not the page's own text
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "template"]):
        tag.decompose()
    for tag in soup(["nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    full_text = re.sub(r"\s+", " ", " ".join(root.stripped_strings)).strip()

    # money signs and codes are hints about the country
    currencies = [s for s in CURRENCY_SYMBOLS if s in full_text]
    currencies += [c for c in CURRENCY_CODES if re.search(rf"\b{c}\b", full_text)]

    return PageInfo(
        url=url,
        host=urlparse(url).netloc.lower(),
        title=title,
        description=description,
        site_name=meta("property", "og:site_name"),
        lang=lang,
        locale=meta("property", "og:locale"),
        currencies=currencies,
        text=full_text[:MAX_TEXT_CHARS],
        thin=len(full_text) < THIN_TEXT_CHARS,
    )


# Download and read one page
def read_page(url, http=requests):
    return extract_page(fetch_page(url, http), url)
