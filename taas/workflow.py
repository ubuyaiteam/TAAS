"""Phase 4: the steps behind the screens. No screen code lives here, so it can be tested.

Order of use: save settings -> sign in -> pick blog -> analyze -> generate -> (edit) -> post.
"""

import dataclasses  # copy a settings object with changes
import re  # split text
import time  # clock
from urllib.parse import urlparse  # read web addresses
import webbrowser  # open the browser
from dataclasses import dataclass, field  # simple data classes
from typing import List  # type hints

from . import __version__, config, updates  # settings, app version, update check
from .anchors import choose_anchors  # pick link keywords
from .article import ArticleRequest, Link, generate_article  # write the article
from .auth import GoogleAuth, TokenStore, load_client_config, sign_in  # Google sign-in
from .blogger import BloggerClient  # Blogger
from .checks import CheckReport, run_checks  # automatic checks
from .detect import analyze_urls, summarize  # find brand, category, country
from .editor import html_to_text, make_image_line, swap_anchor, text_to_html  # editable text
from .errors import ConfigError, ValidationError  # our error types
from .gemini import GeminiClient  # Gemini
from .openai import OpenAIClient
from .inputs import validate_keywords, validate_urls  # input checks
from .pagereader import PageInfo, read_page  # read web pages
from .safeguards import PostLog  # posting limit and repeat warning
from .self_update import install_update  # safely replace a packaged Windows executable
from .terms import forbidden_terms  # brand and domain names to block


# What the page reading found (the user may correct it)
@dataclass
class Analysis:
    urls: List[str]
    keywords: List[str]
    analyses: list  # one UrlAnalysis per address
    category: str = ""
    country: str = ""
    brands: List[str] = field(default_factory=list)


# The article being reviewed
@dataclass
class Draft:
    title: str
    text: str  # editable text (see editor.py)
    links: List[Link]
    keywords: List[str]
    urls: List[str]
    category: str
    country: str
    forbidden: List[str]
    page_notes: List[str]
    min_words: int
    max_words: int
    report: CheckReport
    attempts: int = 1
    humanized: bool = False


# What Blogger answered after posting
@dataclass
class PostResult:
    url: str
    status: str
    live: bool


# Split keywords typed on lines or separated by commas
def split_keywords(text):
    return [part.strip() for part in re.split(r"[\n,]", text or "") if part.strip()]


# Read a whole number typed by the user
def _to_int(raw, label):
    try:
        return int(str(raw).strip())
    except ValueError:
        raise ConfigError(f"{label} must be a whole number.")


class Workflow:
    """All actions the screens can ask for."""

    def __init__(self, gemini_factory=None, blogger_factory=None, reader=read_page,
                 sign_in_fn=sign_in, now=time.time, rng=None, open_browser=webbrowser.open,
                 update_check=updates.check_for_update):
        # the "factory" and "fn" arguments let tests replace the real services
        self.settings = config.load_settings()
        self.store = TokenStore(config.token_path())
        self.log = PostLog(config.app_dir() / "post_log.json")
        self._gemini_factory = gemini_factory
        self._blogger_factory = blogger_factory
        self.reader = reader
        self._sign_in = sign_in_fn
        self.now = now
        self.rng = rng
        self.open_browser = open_browser
        self._update_check = update_check

    # ---------------------------------------------------------- settings

    # Save the values typed on the Setup screen
    def save_settings(self, gemini_key, model, min_words, max_words, post_limit, provider=None,
                      openai_key=None, openai_model=None):
        limit = str(post_limit or "").strip()
        provider = (provider or self.settings.ai_provider or "gemini").strip().lower()
        updated = dataclasses.replace(
            self.settings,
            ai_provider=provider,
            gemini_api_key=(gemini_key or "").strip(),
            gemini_model=(model or "").strip() or config.DEFAULT_GEMINI_MODEL,
            openai_api_key=self.settings.openai_api_key if openai_key is None else (openai_key or "").strip(),
            openai_model=(
                self.settings.openai_model if openai_model is None else
                (openai_model or "").strip() or config.DEFAULT_OPENAI_MODEL
            ),
            min_words=_to_int(min_words, "Minimum words"),
            max_words=_to_int(max_words, "Maximum words"),
            post_limit_per_day=_to_int(limit, "Posting limit") if limit else None,
        )
        config.save_settings(updated)  # checks the values too
        self.settings = updated

    # Is the Google client file there and valid?
    def client_file_status(self):
        try:
            load_client_config(self.settings.client_secret_path())
            return True, "Google client file found."
        except ConfigError as error:
            return False, str(error)

    # What is still missing before the user can start (empty list = ready)
    def missing_setup(self):
        missing = []
        if self.settings.ai_provider == "openai":
            if not self.settings.openai_api_key:
                missing.append("Enter and save your OpenAI API key.")
        elif not self.settings.gemini_api_key:
            missing.append("Enter and save your Gemini API key.")
        if not self.is_signed_in():
            missing.append("Sign in with Google.")
        if not self.settings.blog_id:
            missing.append("Choose your Blogger blog.")
        return missing

    # ------------------------------------------------------------- theme

    # Remember light / dark / system (a wrong value is ignored and "system" is kept)
    def set_theme_mode(self, mode):
        mode = (mode or "").strip().lower()
        if mode not in config.THEME_MODES:
            raise ValidationError("The theme must be System, Light or Dark.")
        config.save_setting(config.KEY_THEME, mode)
        self.settings = dataclasses.replace(self.settings, theme_mode=mode)

    # ----------------------------------------------------------- updates

    # The version of the running app
    @property
    def version(self):
        return __version__

    # Can we look for updates (is a GitHub repository known)?
    def update_check_ready(self):
        return bool(updates.pick_repo(self.settings.update_repo))

    # Ask GitHub whether a newer version was released; returns an UpdateInfo
    def check_for_update(self):
        repo = updates.pick_repo(self.settings.update_repo)
        return self._update_check(__version__, repo, token=self.settings.update_token)

    # Open the download page of a release
    def open_download_page(self, info):
        self.open_browser(info.url)

    # Install a verified release and let the updater restart the app
    def install_update(self, info):
        return install_update(info, token=self.settings.update_token)

    # ------------------------------------------------------------ Google

    def is_signed_in(self):
        return self.store.is_signed_in()

    # Open the browser and sign in
    def sign_in(self):
        client = load_client_config(self.settings.client_secret_path())
        self._sign_in(client, self.store, open_browser=self.open_browser)

    # Forget the account (and the chosen blog)
    def sign_out(self):
        self.store.clear()
        config.save_setting(config.KEY_BLOG_ID, "")
        self.settings = dataclasses.replace(self.settings, blog_id="")

    def _blogger(self):
        if self._blogger_factory:
            return self._blogger_factory()
        client = load_client_config(self.settings.client_secret_path())
        return BloggerClient(GoogleAuth(client, self.store).access_token)

    # The user's blogs
    def list_blogs(self):
        return self._blogger().list_blogs()

    # Remember the chosen blog
    def select_blog(self, blog_id):
        config.save_setting(config.KEY_BLOG_ID, blog_id)
        self.settings = dataclasses.replace(self.settings, blog_id=blog_id)

    # ------------------------------------------------------------ Gemini

    def _gemini(self):
        if self.settings.ai_provider == "openai" and not self.settings.openai_api_key:
            raise ConfigError("The OpenAI API key is missing. Enter it in Setup.")
        if self.settings.ai_provider != "openai" and not self.settings.gemini_api_key:
            raise ConfigError("The Gemini API key is missing. Enter it in Setup.")
        if self._gemini_factory:
            return self._gemini_factory(self.settings)
        if self.settings.ai_provider == "openai":
            return OpenAIClient(self.settings.openai_api_key, self.settings.openai_model)
        return GeminiClient(self.settings.gemini_api_key, self.settings.gemini_model)

    # ------------------------------------------------- step 1: read pages

    # Check the input, read the pages, detect brand / category / country
    def analyze(self, raw_urls, raw_keywords):
        urls = validate_urls(raw_urls)
        keywords = validate_keywords(split_keywords(raw_keywords))
        gemini = self._gemini()
        analyses = analyze_urls(urls, gemini, reader=self.reader)
        category, country, brands = summarize(analyses)
        return Analysis(urls, keywords, analyses, category, country, brands)

    # ----------------------------------------------- step 2: write article

    # Write the first version (the user has corrected category / country / brands)
    def generate(self, analysis, category, country, brands):
        category, country = (category or "").strip(), (country or "").strip()
        if not category:
            raise ValidationError("Type the category of the pages.")
        if not country:
            raise ValidationError("Type the country.")
        gemini = self._gemini()
        pages = [self._page_with_note(a) for a in analysis.analyses]
        anchors = choose_anchors(analysis.keywords, analysis.urls, pages, gemini)
        draft = Draft(
            title="", text="",
            links=[Link(u, a) for u, a in zip(analysis.urls, anchors)],
            keywords=list(analysis.keywords), urls=list(analysis.urls),
            category=category, country=country,
            forbidden=forbidden_terms([b for b in brands if b and b.strip()], analysis.urls),
            page_notes=[" ".join(x for x in (p.title, p.description) if x)[:300] if p else "" for p in pages],
            min_words=self.settings.min_words, max_words=self.settings.max_words,
            report=CheckReport(),
        )
        return self._write(draft, gemini)

    # The page, with the user's own note used as its description (the note wins over the page)
    @staticmethod
    def _page_with_note(item):
        note = (item.detection.note or "").strip()
        if not note:
            return item.page
        if item.page is None:  # the page could not be read: build a small page from the note
            return PageInfo(url=item.url, host=urlparse(item.url).netloc.lower(), description=note)
        return dataclasses.replace(item.page, description=note)

    # Write again with the same links
    def regenerate(self, draft):
        return self._write(draft, self._gemini())

    def _write(self, draft, gemini):
        request = ArticleRequest(
            keywords=list(draft.keywords), links=draft.links, category=draft.category,
            country=draft.country, page_notes=draft.page_notes, min_words=draft.min_words,
            max_words=draft.max_words, forbidden=list(draft.forbidden),
        )
        result = generate_article(request, gemini, rng=self.rng)
        draft.title = result.title
        draft.text = html_to_text(result.html)
        draft.report = result.report
        draft.attempts, draft.humanized = result.attempts, result.humanized
        return draft

    # --------------------------------------------------- step 3: review

    # Check the text the user edited (checks only warn, they never block)
    def recheck(self, draft, title, text):
        html_text, notes = text_to_html(text, draft.links)
        report = run_checks(html_text, title, draft.keywords, draft.links, draft.forbidden,
                            draft.min_words, draft.max_words)
        problems = notes + report.problems
        draft.title, draft.text = title, text
        draft.report = CheckReport(not problems, problems, report.words)
        return html_text, draft.report

    # Use another keyword as the link text; returns the new text
    def change_anchor(self, draft, text, index, new_keyword):
        by_lower = {k.lower(): k for k in draft.keywords}
        keyword = by_lower.get((new_keyword or "").strip().lower())
        if keyword is None:
            raise ValidationError(f"'{new_keyword}' is not one of the keywords.")
        for i, link in enumerate(draft.links):
            if i != index and link.anchor.lower() == keyword.lower():
                raise ValidationError(f"'{keyword}' is already the link text for another address.")
        new_text = swap_anchor(text, draft.links[index].anchor, keyword)  # may raise; nothing changed yet
        draft.links[index].anchor = keyword
        draft.text = new_text
        return new_text

    # The text line for a picture (the Article screen puts it into the text)
    @staticmethod
    def image_line(url, alt=""):
        return make_image_line(url, alt)

    # Things the user should know before posting
    def warnings_before_post(self, draft, title, text):
        _, report = self.recheck(draft, title, text)
        warnings = []
        if not report.passed:
            warnings.append(
                f"The article still has {len(report.problems)} check problem(s):\n"
                + "\n".join(f"- {p}" for p in report.problems)
            )
        repeat = self.log.repeat_warning(draft.urls, self.now())
        if repeat:
            warnings.append(repeat)
        return warnings

    # ------------------------------------------------------ step 4: post

    # Post to Blogger (live=False saves a Blogger draft)
    def post(self, draft, title, text, live, confirmed):
        if not confirmed:
            raise ValidationError("Tick the box to confirm you have read the article.")
        if not (title or "").strip():
            raise ValidationError("The article needs a title.")
        if not (text or "").strip():
            raise ValidationError("The article has no text.")
        blog_id = self.settings.blog_id
        if not blog_id:
            raise ConfigError("No blog is chosen. Choose one in Setup.")
        now = self.now()
        if live:
            self.log.check_limit(self.settings.post_limit_per_day, blog_id, now)

        html_text, _ = self.recheck(draft, title, text)
        post = self._blogger().create_post(blog_id, title, html_text, draft=not live)
        try:
            self.log.record(blog_id, draft.urls, live, now)
        except OSError:
            pass  # the post worked; a log problem must not hide that
        return PostResult(post.url, post.status, live)
