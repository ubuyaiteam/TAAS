"""Phase 2 + 3 live check. Run on your own PC (needs internet and a Gemini key).

    python phase23_check.py --url URL1 --url URL2 --keywords "kw1, kw2, kw3, kw4, kw5"
    python phase23_check.py ... --category "office furniture" --country India   # fix detected values
    python phase23_check.py ... --post-draft    # also save the article as a Blogger DRAFT (needs Phase 1 sign-in)

It reads the pages, finds brand/category/country, picks the link keywords, writes the
article, runs the checks, and saves article_preview.html next to this script.
"""

import argparse  # read command options
import html  # make text safe inside HTML
import sys  # exit code
from pathlib import Path  # file paths

from taas import config  # settings
from taas.anchors import choose_anchors  # pick link keywords
from taas.article import ArticleRequest, Link, generate_article  # write the article
from taas.auth import GoogleAuth, TokenStore, load_client_config  # Google sign-in (Phase 1)
from taas.blogger import BloggerClient  # Blogger (Phase 1)
from taas.detect import analyze_urls, summarize  # find brand, category, country
from taas.errors import ConfigError, TaasError, ValidationError  # our error types
from taas.gemini import GeminiClient  # Gemini
from taas.inputs import validate_keywords, validate_urls  # input checks
from taas.terms import forbidden_terms  # brand and domain names to block


# Make printing safe for any letters (the Windows console can fail on some)
def make_console_safe():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


# Run the live check
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", action="append", default=[], help="web address to link to (use 2 or 3 times)")
    parser.add_argument("--keywords", default="", help="5 to 10 keywords, separated by commas")
    parser.add_argument("--category", default="", help="use this instead of the detected category")
    parser.add_argument("--country", default="", help="use this instead of the detected country")
    parser.add_argument("--post-draft", action="store_true", help="also save the article as a Blogger draft")
    args = parser.parse_args()

    make_console_safe()
    try:
        # check the input first
        urls = validate_urls(args.url)
        keywords = validate_keywords(args.keywords.split(","))

        settings = config.load_settings()
        gemini = GeminiClient(settings.gemini_api_key, settings.gemini_model)
        print(f"Using Gemini model: {settings.gemini_model}")

        # ---- Phase 2: read pages, detect brand / category / country ----
        print("\n1. Reading the pages and detecting details...")
        analyses = analyze_urls(urls, gemini)
        for a in analyses:
            d = a.detection
            print(f"   {a.url}")
            if d.error:
                print(f"     PROBLEM: {d.error}")
            else:
                print(f"     brand={d.brand!r}  category={d.category!r}  country={d.country!r}"
                      + ("  (page had little text)" if d.thin else ""))
        category, country, brands = summarize(analyses)
        category = args.category or category
        country = args.country or country
        if not category or not country:
            raise ValidationError("Category or country was not detected. Add --category and --country.")
        print(f"   -> article category: {category} | country: {country}")

        # ---- Phase 3: pick anchors, write, check ----
        print("\n2. Choosing the link keyword for each address...")
        pages = [a.page for a in analyses]
        anchors = choose_anchors(keywords, urls, pages, gemini)
        links = [Link(u, k) for u, k in zip(urls, anchors)]
        for link in links:
            print(f"   '{link.anchor}' -> {link.url}")

        forbidden = forbidden_terms(brands, urls)
        print(f"   Names that must not appear: {', '.join(forbidden) or '(none found)'}")

        notes = [f"{p.title}. {p.description}"[:300] if p else "" for p in pages]
        request = ArticleRequest(
            keywords=keywords, links=links, category=category, country=country,
            page_notes=notes, min_words=settings.min_words, max_words=settings.max_words,
            forbidden=forbidden,
        )
        print("\n3. Writing the article (this can take a minute)...")
        result = generate_article(request, gemini)

        print(f"\nTITLE: {result.title}")
        print(f"Words: {result.report.words} | tries: {result.attempts} | humanized: {result.humanized}")
        if result.report.passed:
            print("CHECKS: all passed")
        else:
            print("CHECKS: problems left (fix these by hand on the review screen):")
            for problem in result.report.problems:
                print(f"   - {problem}")

        preview = Path(__file__).with_name("article_preview.html")
        preview.write_text(
            f"<html><head><meta charset='utf-8'><title>{html.escape(result.title)}</title></head>"
            f"<body style='max-width:700px;margin:2em auto;font-family:sans-serif'>"
            f"<h1>{html.escape(result.title)}</h1>{result.html}</body></html>",
            encoding="utf-8",
        )
        print(f"\nSaved {preview.name}. Open it in your browser and click each link.")

        # ---- optional: save as a Blogger draft ----
        if args.post_draft:
            if not settings.blog_id:
                raise ConfigError("No blog selected yet. Run phase1_check.py first.")
            client = load_client_config(settings.client_secret_path())
            blogger = BloggerClient(GoogleAuth(client, TokenStore(config.token_path())).access_token)
            post = blogger.create_post(settings.blog_id, result.title, result.html, draft=True)
            print(f"Saved as a Blogger DRAFT: {post.url or post.id}")
        return 0 if result.report.passed else 2
    # show friendly errors only
    except TaasError as error:
        print(f"\nCHECK FAILED: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
