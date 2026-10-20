"""Phase 3: write the article with Gemini, add the links, check it, retry if needed."""

import html  # make text safe inside HTML
import random  # vary the article between runs
import re  # find patterns in text
from dataclasses import dataclass, field  # simple data classes
from typing import List  # type hints

from .checks import MAX_HEADINGS, MAX_KEYWORD_USES, MIN_HEADINGS, CheckReport, run_checks  # checks and their limits
from .errors import ConfigError, GeminiError, ValidationError  # our error types
from .gemini import parse_json_reply  # turn Gemini's text into JSON
from .htmlutil import sanitize_html  # keep only safe tags
from .inputs import MAX_URLS, MIN_URLS, normalize_url, validate_keywords  # input checks
from .terms import redact  # hide brand names

MAX_ATTEMPTS = 3  # how many times we may write the article again
TEMPERATURE = 0.9  # higher = more varied wording

# different angles so two articles on the same topic do not look alike
ANGLES = [
    "practical tips a beginner can use right away",
    "common mistakes people make and how to avoid them",
    "a simple checklist to follow before deciding",
    "questions people often ask, answered simply",
    "things to know before starting",
]
STRUCTURES = [
    "a short intro, then sections that each solve one small problem, then a short ending",
    "a short intro that names a common problem, sections with steps, then a calm ending",
    "a friendly intro, sections that compare options in plain words, then a short summary",
]

SYSTEM = (
    "You write helpful, plain and honest articles for ordinary readers. "
    "The article gives information. It is not an advertisement. "
    "Never mention any brand, company, store or product name. "
    "Never invent facts, statistics, prices, laws or claims. "
    "Never write web addresses. Return only the JSON that is asked for."
)


# One link: the web address and the keyword used as link text
@dataclass
class Link:
    url: str
    anchor: str


# Everything needed to write one article
@dataclass
class ArticleRequest:
    keywords: List[str]  # 5-10 keywords
    links: List[Link]  # 2-3 links
    category: str  # what the pages are about
    country: str  # reader's country
    page_notes: List[str] = field(default_factory=list)  # short notes on each page
    min_words: int = 300  # shortest body
    max_words: int = 400  # longest body
    forbidden: List[str] = field(default_factory=list)  # brand and domain names to block


# One written version of the article
@dataclass
class Candidate:
    title: str
    html: str
    report: CheckReport
    humanized: bool = False


# The final result
@dataclass
class ArticleResult:
    title: str
    html: str
    report: CheckReport  # report.passed False = the user must fix the listed problems
    attempts: int
    humanized: bool


# Check the request; also cleans the keywords and the link texts
def validate_request(req):
    req.keywords = validate_keywords(req.keywords)
    if not MIN_URLS <= len(req.links) <= MAX_URLS:
        raise ValidationError(f"The article needs {MIN_URLS} to {MAX_URLS} links.")
    by_lower = {k.lower(): k for k in req.keywords}
    seen = set()
    for link in req.links:
        normalize_url(link.url)
        key = link.anchor.strip().lower()
        if key not in by_lower:
            raise ValidationError(f"The link text '{link.anchor}' is not one of the keywords.")
        if key in seen:
            raise ValidationError(f"The link text '{link.anchor}' is used for two links.")
        seen.add(key)
        link.anchor = by_lower[key]  # use the keyword exactly as typed
    if not 1 <= req.min_words <= req.max_words:
        raise ValidationError("The word range is not valid.")


# Build the writing request for Gemini
def build_prompt(req, angle, structure, problems=None):
    anchors = {l.anchor.lower() for l in req.links}
    others = [k for k in req.keywords if k.lower() not in anchors]
    target = (req.min_words + req.max_words) // 2
    link_lines = "\n".join(
        f'- Link {i}: write the phrase "{l.anchor}" exactly once as [[L{i}]]{l.anchor}[[/L{i}]] '
        "inside a normal sentence of a body paragraph (not in a heading)."
        for i, l in enumerate(req.links, 1)
    )
    notes = "\n".join(f"- {redact(n, req.forbidden)}" for n in req.page_notes if n) or "- (none)"
    text = (
        f"Topic area: {req.category}\n"
        f"Reader's country: {req.country} (use it only for tone and spelling; do not invent local facts)\n"
        f"Keywords: {'; '.join(req.keywords)}\n\n"
        "Rules for the keywords:\n"
        "- Use every keyword at least once, exactly as written, inside natural sentences.\n"
        f"- Use no keyword more than {MAX_KEYWORD_USES} times. Do not repeat the same phrase.\n"
        "- You may also use close, natural related words so the text does not sound repeated.\n"
        f"- Keywords that are not links: {'; '.join(others) or '(none)'}\n\n"
        f"Links (each must appear exactly once):\n{link_lines}\n\n"
        f"Background notes about the linked pages (do not copy names from them):\n{notes}\n\n"
        f"Angle: {angle}.\nShape: {structure}.\n"
        f"Length: the body must be between {req.min_words} and {req.max_words} words. Aim for about {target}.\n"
        "Format: body_html uses only <p> and <h2> (and <ul><li> if needed). "
        f"Use {MIN_HEADINGS} or {MAX_HEADINGS} <h2> subheadings. Write in an easy, friendly, human voice.\n"
        "Do not sell. No hype, no discounts, no calls to buy.\n"
        'Return JSON: {"title": "...", "body_html": "..."}'
    )
    if problems:
        text += "\n\nYour last try had these problems. Fix all of them:\n" + "\n".join(f"- {p}" for p in problems)
    return text


# Build the rewrite request (second pass)
def build_humanize_prompt(req, title, body_html):
    return (
        "Rewrite the article below so it sounds like a real person wrote it. "
        "Vary the sentence length, use plain everyday words, and remove stock phrases.\n"
        "Keep exactly: every [[L#]]...[[/L#]] marker once each, every keyword phrase as written, "
        f"the number of <h2> headings, and a body length of {req.min_words} to {req.max_words} words.\n"
        "Do not add facts, numbers, brand names or web addresses.\n"
        'Return JSON: {"title": "...", "body_html": "..."}\n\n'
        f"Title: {title}\nbody_html:\n{body_html}"
    )


# Read Gemini's article answer
def _parse_article(text):
    data = parse_json_reply(text)
    title = str(data.get("title", "")).strip()
    body = str(data.get("body_html", "")).strip()
    if not title or not body:
        raise GeminiError("Gemini's article was incomplete.")
    return title, sanitize_html(body)


# Turn the [[L1]]..[[/L1]] markers into real links
def assemble(body_html, links):
    problems = []
    for i, link in enumerate(links, 1):
        pattern = re.compile(rf"\[\[L{i}\]\](.*?)\[\[/L{i}\]\]", re.DOTALL)
        found = pattern.findall(body_html)
        if len(found) != 1:
            problems.append(f"The link marker {i} appears {len(found)} times. It must appear once.")
            continue
        href = html.escape(link.url, quote=True)
        # a function is used so special characters in the address cannot break the replacement
        body_html = pattern.sub(lambda m: f'<a href="{href}">{m.group(1)}</a>', body_html)
    # markers that were left over are removed
    if re.search(r"\[\[/?L\d+\]\]", body_html):
        problems.append("Some link markers were damaged or extra.")
        body_html = re.sub(r"\[\[/?L\d+\]\]", "", body_html)
    return body_html, problems


# Check one version and wrap it as a Candidate
def _evaluate(req, title, body_html, humanized):
    final_html, problems = assemble(body_html, req.links)
    report = run_checks(final_html, title, req.keywords, req.links, req.forbidden, req.min_words, req.max_words)
    problems = problems + report.problems
    return Candidate(title, final_html, CheckReport(not problems, problems, report.words), humanized)


# The version with fewer problems wins (a tie goes to the newer one)
def _better(old, new):
    if old is None or len(new.report.problems) <= len(old.report.problems):
        return new
    return old


# Write once (and humanize); return the better version
def _attempt(req, gemini, angle, structure, problems, humanize):
    reply = gemini.generate(build_prompt(req, angle, structure, problems), system=SYSTEM,
                            temperature=TEMPERATURE, json_mode=True)
    title, body = _parse_article(reply)
    best = _evaluate(req, title, body, False)
    if humanize:
        try:
            second = gemini.generate(build_humanize_prompt(req, title, body), system=SYSTEM,
                                     temperature=TEMPERATURE, json_mode=True)
            h_title, h_body = _parse_article(second)
            best = _better(best, _evaluate(req, h_title, h_body, True))
        except ConfigError:
            raise
        except GeminiError:
            pass  # the first version is still good to use
    return best


# Main step: write, check, retry; always return the best version found
def generate_article(req, gemini, rng=None, max_attempts=MAX_ATTEMPTS, humanize=True):
    validate_request(req)
    rng = rng or random.Random()
    angle, structure = rng.choice(ANGLES), rng.choice(STRUCTURES)  # fixed for all tries of this article

    best, problems, last_error = None, None, None
    for attempt in range(1, max_attempts + 1):
        try:
            candidate = _attempt(req, gemini, angle, structure, problems, humanize)
        except ConfigError:
            raise  # a wrong key or model stops everything
        except GeminiError as error:
            last_error = error
            continue
        best = _better(best, candidate)
        if candidate.report.passed:
            return ArticleResult(candidate.title, candidate.html, candidate.report, attempt, candidate.humanized)
        problems = candidate.report.problems  # tell Gemini what to fix next time
    if best is None:
        raise last_error or GeminiError("The article could not be written.")
    return ArticleResult(best.title, best.html, best.report, max_attempts, best.humanized)
