"""Brand names and domain names that must never appear in the article."""

import re  # find patterns in text
from urllib.parse import urlparse  # read web addresses

SECOND_LEVEL = {"co", "com", "org", "net", "gov", "edu", "ac"}  # like the "co" in example.co.uk
MIN_DOMAIN_LABEL = 3  # shorter names (like "t" in t.co) would match too much
MIN_BRAND = 2  # shortest brand name we block


# Domain terms of one web address: full host and main name
def domain_terms(url):
    host = urlparse(url).netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    terms = {host}
    labels = host.split(".")
    if len(labels) >= 2:
        # example.co.uk -> "example"; shop.example.com -> "example"
        if len(labels) >= 3 and labels[-2] in SECOND_LEVEL:
            main = labels[-3]
        else:
            main = labels[-2]
        if len(main) >= MIN_DOMAIN_LABEL:
            terms.add(main)
    return {t for t in terms if t}


# All terms to block: brand names plus domain names
def forbidden_terms(brands, urls):
    terms = {b.strip() for b in brands if b and len(b.strip()) >= MIN_BRAND}
    for url in urls:
        terms |= domain_terms(url)
    return sorted(terms, key=str.lower)


# Whole-word match, ignoring upper/lower case
def _pattern(term):
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", re.IGNORECASE)


# Is the term in the text?
def find_term(text, term):
    return bool(_pattern(term).search(text))


# Replace the terms in the text with a neutral word
def redact(text, terms, replacement="the store"):
    for term in terms:
        text = _pattern(term).sub(replacement, text)
    return text
