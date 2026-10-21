"""Phase 3: automatic checks on a finished article."""

import re  # find patterns in text
from collections import Counter  # count repeats
from dataclasses import dataclass, field  # simple data classes
from typing import List  # type hints

from bs4 import BeautifulSoup  # read HTML

from .htmlutil import count_words, visible_text  # text helpers
from .terms import find_term  # whole-word search

MAX_KEYWORD_USES = 3  # a keyword may appear at most this many times
MIN_HEADINGS, MAX_HEADINGS = 2, 3  # subheadings (h2) allowed
REPEAT_LIMIT = 3  # a 4-word phrase seen this many times counts as repeated
# phrases that make a text sound machine-written (you can add more)
STOCK_PHRASES = (
    "in today's fast-paced world", "in today's digital age", "in the ever-evolving",
    "delve into", "dive into", "unlock the power", "game-changer", "game changer",
    "it's important to note", "it is important to note", "tapestry", "navigating the landscape",
    "in conclusion,", "look no further", "take your", "to the next level",
)


# The result of the checks
@dataclass
class CheckReport:
    passed: bool = False  # True when there are no problems
    problems: List[str] = field(default_factory=list)  # plain-language problems
    words: int = 0  # word count of the body


# How many times the phrase appears (whole words, any letter case)
def _uses(text, phrase):
    return len(re.findall(r"(?<![A-Za-z0-9])" + re.escape(phrase) + r"(?![A-Za-z0-9])", text, re.IGNORECASE))


# Run every check; links = list of objects with .url and .anchor
def run_checks(html_text, title, keywords, links, forbidden, min_words, max_words):
    problems = []
    soup = BeautifulSoup(html_text, "html.parser")
    text = visible_text(html_text)
    words = count_words(text)

    # 1. title
    if not (title or "").strip():
        problems.append("The article has no title.")

    # 2. length
    if not min_words <= words <= max_words:
        problems.append(f"The article has {words} words. It must be {min_words} to {max_words}.")

    # 3. structure: 2-3 subheadings
    headings = len(soup.find_all("h2"))
    if not MIN_HEADINGS <= headings <= MAX_HEADINGS:
        problems.append(f"The article has {headings} subheadings. It needs {MIN_HEADINGS} to {MAX_HEADINGS}.")

    # 4. keywords: each present, none used too often
    for keyword in keywords:
        count = _uses(text, keyword)
        if count == 0:
            problems.append(f"The keyword '{keyword}' is missing.")
        elif count > MAX_KEYWORD_USES:
            problems.append(f"The keyword '{keyword}' is used {count} times. The most allowed is {MAX_KEYWORD_USES}.")

    # 5. links: exactly one per web address, right text, no extras
    anchors = soup.find_all("a")
    if len(anchors) != len(links):
        problems.append(f"The article has {len(anchors)} links. It needs exactly {len(links)}.")
    for link in links:
        found = [a for a in anchors if (a.get("href") or "") == link.url]
        if len(found) != 1:
            problems.append(f"The link to {link.url} appears {len(found)} times. It must appear once.")
        elif found[0].get_text(strip=True).lower() != link.anchor.lower():
            problems.append(f"The link to {link.url} must use the text '{link.anchor}'.")
    if re.search(r"https?://|www\.", text, re.IGNORECASE):
        problems.append("The text contains a web address. Links must be words only.")

    # 6. no brand or domain names (title and text; link addresses are allowed)
    for term in forbidden:
        if find_term(text, term) or find_term(title or "", term):
            problems.append(f"The name '{term}' must not appear in the article.")

    # 6b. picture descriptions are read by search engines, so brand names must stay out of them too
    for image in soup.find_all("img"):
        for term in forbidden:
            if find_term(image.get("alt") or "", term):
                problems.append(f"The name '{term}' must not appear in a picture description.")

    # 7. repeated phrases (4-word groups)
    tokens = re.findall(r"[a-z0-9']+", text.lower())
    keyword_texts = [" ".join(k.lower().split()) for k in keywords]
    grams = Counter(" ".join(tokens[i:i + 4]) for i in range(len(tokens) - 3))
    for gram, count in grams.items():
        if count >= REPEAT_LIMIT and not any(gram in k for k in keyword_texts):
            problems.append(f"The phrase '{gram}' is repeated {count} times.")
            break  # one example is enough

    # 8. stock phrases
    lowered = text.lower().replace("\u2019", "'")
    for phrase in STOCK_PHRASES:
        if phrase in lowered:
            problems.append(f"The article uses the stock phrase '{phrase}'.")

    return CheckReport(passed=not problems, problems=problems, words=words)
