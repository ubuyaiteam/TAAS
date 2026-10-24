"""Shared helpers for the Phase 2 and 3 tests."""

import json  # write JSON answers
import random  # make test text
import re  # find patterns in text

from taas.article import Link  # one link

KEYWORDS = ["great deals", "home office", "desk setup", "budget tips", "buying guide"]  # sample keywords
URLS = ["https://shop-one.example.com/desks", "https://www.second-site.co.uk/guides/chairs"]  # sample pages
VOCAB = [f"term{i}x" for i in range(800)]  # made-up words, so no phrase repeats by accident


# Two sample links (anchor = keyword)
def sample_links():
    return [Link(URLS[0], "great deals"), Link(URLS[1], "buying guide")]


# A sentence of made-up words, with an optional keyword in the middle
def sentence(rng, size, keyword=""):
    left = " ".join(rng.choice(VOCAB) for _ in range(size // 2))
    right = " ".join(rng.choice(VOCAB) for _ in range(size - size // 2))
    return f"{left} {keyword} {right}.".replace("  ", " ")


# Build a good article body with link markers; about `target` words
def make_body(keywords=KEYWORDS, links=None, target=340, seed=1):
    rng = random.Random(seed)
    links = links if links is not None else sample_links()
    anchors = {l.anchor: i for i, l in enumerate(links, 1)}
    parts = []
    for kw in keywords:
        marked = f"[[L{anchors[kw]}]]{kw}[[/L{anchors[kw]}]]" if kw in anchors else kw
        parts.append(sentence(rng, 14, marked))
    # fill with made-up sentences until the word count is right
    def words():
        text = re.sub(r"\[\[/?L\d+\]\]", "", " ".join(parts))
        return len(text.split())
    while words() < target - 6:
        parts.append(sentence(rng, 18))
    third = max(1, len(parts) // 3)
    p = lambda chunk: "<p>" + " ".join(chunk) + "</p>"
    return (
        p(parts[:third])
        + "<h2>First part</h2>" + p(parts[third:2 * third])
        + "<h2>Second part</h2>" + p(parts[2 * third:])
    )


# Wrap title and body as Gemini's JSON answer
def reply(title="A helpful guide", body=None):
    return json.dumps({"title": title, "body_html": body if body is not None else make_body()})


# A fake Gemini: returns the prepared answers one by one and keeps the prompts
class FakeGemini:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def generate(self, prompt, system="", temperature=None, json_mode=False):
        self.calls.append({"prompt": prompt, "system": system, "temperature": temperature, "json_mode": json_mode})
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
