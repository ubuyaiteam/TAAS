"""Phase 3: choose which keyword becomes the link text for each web address."""

import re  # find patterns in text
from urllib.parse import urlparse  # read web addresses

from .errors import ConfigError, GeminiError  # our error types
from .gemini import parse_json_reply  # turn Gemini's text into JSON

SYSTEM = "You match keywords to web pages. Use only the details given. Return only JSON."


# Words of a text (lowercase, longer than 2 letters)
def _words(text):
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


# What we know about a page, as one short text
def page_text(url, page):
    path = urlparse(url).path.replace("-", " ").replace("_", " ").replace("/", " ")
    if page is None:
        return path
    return f"{page.title} {page.description} {page.text[:600]} {path}"


# Backup way: pick the keyword that shares the most words with each page
def choose_by_overlap(keywords, texts):
    page_words = [_words(t) for t in texts]
    pairs = []
    for p, words in enumerate(page_words):
        for k, keyword in enumerate(keywords):
            score = len(_words(keyword) & words)
            pairs.append((-score, p, k))  # best score first, then earlier page, then earlier keyword
    chosen, used = {}, set()
    for _, p, k in sorted(pairs):
        if p not in chosen and k not in used:
            chosen[p] = k
            used.add(k)
    return [keywords[chosen[p]] for p in range(len(texts))]


# Ask Gemini; return None if its answer cannot be used
def _ask_gemini(keywords, urls, texts, gemini):
    lines = "\n".join(f"{i}. {texts[i - 1][:500]}" for i in range(1, len(urls) + 1))
    prompt = (
        "Keywords: " + "; ".join(keywords) + "\n\nPages:\n" + lines + "\n\n"
        "For each page number, choose the ONE keyword from the list that fits that page best. "
        "Use each keyword at most once. Copy the keyword exactly.\n"
        'Return JSON like {"anchors": ["keyword for page 1", "keyword for page 2"]}'
    )
    try:
        data = parse_json_reply(gemini.generate(prompt, system=SYSTEM, json_mode=True))
    except ConfigError:
        raise  # a wrong key or model stops everything
    except GeminiError:
        return None
    answer = data.get("anchors")
    if not isinstance(answer, list) or len(answer) != len(urls):
        return None
    by_lower = {k.lower(): k for k in keywords}
    result = []
    for item in answer:
        keyword = by_lower.get(str(item).strip().lower())
        if keyword is None or keyword in result:
            return None  # not a keyword from the list, or used twice
        result.append(keyword)
    return result


# Pick one keyword per web address (same order as the addresses)
def choose_anchors(keywords, urls, pages, gemini=None):
    texts = [page_text(u, p) for u, p in zip(urls, pages)]
    if gemini is not None:
        picked = _ask_gemini(keywords, urls, texts, gemini)
        if picked:
            return picked
    return choose_by_overlap(keywords, texts)
