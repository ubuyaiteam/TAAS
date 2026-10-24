import json  # write JSON
import os  # environment variables
import random  # fixed random numbers for tests
import tempfile  # temporary folders
import unittest  # test tools
from pathlib import Path  # file paths

from taas import config, workflow  # the code being tested
from taas.blogger import Blog, Post  # Blogger data
from taas.errors import BloggerError, ConfigError, GeminiError, ValidationError  # our error types
from taas.openai import OpenAIClient
from taas.pagereader import PageInfo  # a read page

from tests.helpers import FakeGemini, KEYWORDS, URLS, reply  # test helpers

DETECT = json.dumps({"brand": "Acme", "category": "office furniture", "country": "India"})
ANCHORS = json.dumps({"anchors": ["great deals", "buying guide"]})


# Fake Blogger: keeps what was posted
class FakeBlogger:
    def __init__(self, error=None):
        self.posts, self.error = [], error

    def list_blogs(self):
        return [Blog("111", "My blog", "https://my.blogspot.com/")]

    def create_post(self, blog_id, title, html, draft=True):
        if self.error:
            raise self.error
        self.posts.append({"blog_id": blog_id, "title": title, "html": html, "draft": draft})
        return Post("p1", "https://my.blogspot.com/p.html", "DRAFT" if draft else "LIVE")


# A fake page reader
def fake_reader(url, http):
    return PageInfo(url=url, host="shop.example.com", title="Desks", description="Good desks", text="Desks. " * 40, lang="en")


class WorkflowBase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        old = os.environ.get("TAAS_HOME")
        os.environ["TAAS_HOME"] = str(self.home)
        self.addCleanup(lambda: os.environ.__setitem__("TAAS_HOME", old) if old else os.environ.pop("TAAS_HOME", None))
        self.clock = 1_000_000.0
        self.blogger = FakeBlogger()
        self.gem = FakeGemini()
        self.signed_in_with = []
        self.wf = workflow.Workflow(
            gemini_factory=lambda s: self.gem, blogger_factory=lambda: self.blogger, reader=fake_reader,
            sign_in_fn=lambda client, store, open_browser=None: self.signed_in_with.append(client.client_id),
            now=lambda: self.clock, rng=random.Random(1),
        )

    # Settings with a key and a blog
    def ready(self, limit=""):
        self.wf.save_settings("KEY", "", "300", "400", limit)
        self.wf.select_blog("111")

    # Run steps 1 and 2 with scripted Gemini answers
    def make_draft(self):
        self.gem.replies += [DETECT, DETECT, ANCHORS, reply(), reply()]
        analysis = self.wf.analyze(list(URLS), "\n".join(KEYWORDS))
        return self.wf.generate(analysis, analysis.category, analysis.country, analysis.brands)


# Tests for settings, sign-in and blogs
class SetupTests(WorkflowBase):
    def test_save_settings_round_trip(self):
        self.wf.save_settings(" KEY ", "my-model", "250", "450", "2")
        loaded = config.load_settings()
        self.assertEqual((loaded.gemini_api_key, loaded.gemini_model, loaded.min_words, loaded.max_words, loaded.post_limit_per_day),
                         ("KEY", "my-model", 250, 450, 2))

    def test_openai_settings_select_and_require_openai_key(self):
        self.wf.save_settings("", "", "300", "400", "", provider="openai",
                              openai_key=" sk-openai ", openai_model="gpt-test")
        loaded = config.load_settings()
        self.assertEqual((loaded.ai_provider, loaded.openai_api_key, loaded.openai_model),
                         ("openai", "sk-openai", "gpt-test"))
        self.assertEqual(loaded.gemini_api_key, "")
        self.assertEqual(self.wf.missing_setup()[0], "Sign in with Google.")

    def test_openai_provider_missing_key_is_reported_and_client_is_selected(self):
        self.wf.save_settings("", "", "300", "400", "", provider="openai", openai_key="")
        self.assertIn("Enter and save your OpenAI API key.", self.wf.missing_setup())
        with self.assertRaisesRegex(ConfigError, "OpenAI API key"):
            self.wf._gemini()

    def test_openai_provider_builds_openai_client(self):
        self.wf.save_settings("", "", "300", "400", "", provider="openai", openai_key="OPENAI")
        self.wf._gemini_factory = None
        client = self.wf._gemini()
        self.assertIsInstance(client, OpenAIClient)
        self.assertEqual((client.api_key, client.model), ("OPENAI", config.DEFAULT_OPENAI_MODEL))

    def test_blank_model_and_limit_use_defaults(self):
        self.wf.save_settings("KEY", " ", "300", "400", "")
        self.assertEqual(self.wf.settings.gemini_model, config.DEFAULT_GEMINI_MODEL)
        self.assertIsNone(self.wf.settings.post_limit_per_day)

    def test_bad_settings_are_rejected_and_nothing_changes(self):
        for args in (("K", "", "abc", "400", ""), ("K", "", "500", "400", ""), ("K", "", "300", "400", "0"), ("K", "", "300", "400", "x")):
            with self.assertRaises(ConfigError):
                self.wf.save_settings(*args)
        self.assertEqual(self.wf.settings.gemini_api_key, "")

    def test_saving_keeps_the_chosen_blog(self):
        self.wf.select_blog("111")
        self.wf.save_settings("KEY", "", "300", "400", "")
        self.assertEqual(config.load_settings().blog_id, "111")

    def test_missing_setup_list(self):
        self.assertEqual(len(self.wf.missing_setup()), 3)
        self.ready()
        self.wf.store.save({"access_token": "a", "refresh_token": "r"})
        self.assertEqual(self.wf.missing_setup(), [])

    def test_client_file_status(self):
        ok, message = self.wf.client_file_status()
        self.assertFalse(ok)
        self.assertIn("not found", message)
        (self.home / "client_secret.json").write_text(json.dumps({"installed": {"client_id": "cid", "client_secret": "s"}}))
        self.assertTrue(self.wf.client_file_status()[0])

    def test_sign_in_and_sign_out(self):
        (self.home / "client_secret.json").write_text(json.dumps({"installed": {"client_id": "cid", "client_secret": "s"}}))
        self.wf.sign_in()
        self.assertEqual(self.signed_in_with, ["cid"])
        self.wf.select_blog("111")
        self.wf.store.save({"access_token": "a", "refresh_token": "r"})
        self.wf.sign_out()
        self.assertFalse(self.wf.is_signed_in())
        self.assertEqual(config.load_settings().blog_id, "")

    def test_sign_in_without_client_file(self):
        with self.assertRaises(ConfigError):
            self.wf.sign_in()

    def test_blog_list(self):
        self.assertEqual(self.wf.list_blogs()[0].name, "My blog")


# Tests for reading pages and writing the article
class WriteTests(WorkflowBase):
    def test_bad_input_stops_before_gemini(self):
        self.ready()
        for urls, kws in ((["https://a.com"], "a,b,c,d,e"), (list(URLS), "a,b")):
            with self.assertRaises(ValidationError):
                self.wf.analyze(urls, kws)
        self.assertEqual(self.gem.calls, [])

    def test_missing_gemini_key(self):
        with self.assertRaises(ConfigError):
            self.wf.analyze(list(URLS), "\n".join(KEYWORDS))

    def test_analyze_and_generate(self):
        self.ready()
        self.gem.replies += [DETECT, DETECT]
        analysis = self.wf.analyze(list(URLS), ", ".join(KEYWORDS))
        self.assertEqual((analysis.category, analysis.country, analysis.brands), ("office furniture", "India", ["Acme", "Acme"]))
        self.assertEqual(analysis.keywords, KEYWORDS)

        self.gem.replies += [ANCHORS, reply(), reply()]
        draft = self.wf.generate(analysis, analysis.category, analysis.country, analysis.brands)
        self.assertEqual([l.anchor for l in draft.links], ["great deals", "buying guide"])
        self.assertIn("[great deals]", draft.text)
        self.assertIn("## First part", draft.text)
        self.assertTrue(draft.report.passed, draft.report.problems)
        self.assertIn("Acme", draft.forbidden)
        self.assertIn("example", draft.forbidden)  # from the domain names

    def test_user_corrections_are_used(self):
        self.ready()
        self.gem.replies += [DETECT, DETECT]
        analysis = self.wf.analyze(list(URLS), "\n".join(KEYWORDS))
        self.gem.replies += [ANCHORS, reply(), reply()]
        draft = self.wf.generate(analysis, "home desks", "Canada", ["Globex", ""])
        self.assertIn("Globex", draft.forbidden)
        self.assertNotIn("Acme", draft.forbidden)
        self.assertIn("home desks", self.gem.calls[-2]["prompt"])
        self.assertIn("Canada", self.gem.calls[-2]["prompt"])

    def test_empty_category_or_country(self):
        self.ready()
        self.gem.replies += [DETECT, DETECT]
        analysis = self.wf.analyze(list(URLS), "\n".join(KEYWORDS))
        for category, country in (("", "India"), ("desks", "  ")):
            with self.assertRaises(ValidationError):
                self.wf.generate(analysis, category, country, [])

    def test_word_range_comes_from_settings(self):
        self.wf.save_settings("KEY", "", "100", "200", "")
        self.wf.select_blog("111")
        self.gem.replies += [DETECT, DETECT, ANCHORS, reply(), reply(), reply(), reply(), reply(), reply()]
        analysis = self.wf.analyze(list(URLS), "\n".join(KEYWORDS))
        draft = self.wf.generate(analysis, "desks", "India", [])
        self.assertEqual((draft.min_words, draft.max_words), (100, 200))
        self.assertFalse(draft.report.passed)  # the sample article is too long for 100-200 words

    def test_note_typed_by_the_user_is_used_when_a_page_cannot_be_read(self):
        self.ready()
        from taas.errors import PageReadError  # our error types

        def reader(url, http):
            if url == URLS[0]:
                raise PageReadError("blocked (HTTP 403)")
            return fake_reader(url, http)

        self.wf.reader = reader
        self.gem.replies += [DETECT, ANCHORS, reply(), reply()]  # only the readable page is sent to Gemini
        analysis = self.wf.analyze(list(URLS), "\n".join(KEYWORDS))
        self.assertIn("blocked", analysis.analyses[0].detection.error)
        analysis.analyses[0].detection.note = "Seasonal costume offers for couples"
        draft = self.wf.generate(analysis, "costumes", "Australia", ["Acme"])
        anchors_prompt, article_prompt = self.gem.calls[-3]["prompt"], self.gem.calls[-2]["prompt"]
        self.assertIn("Seasonal costume offers for couples", anchors_prompt)
        self.assertIn("Seasonal costume offers for couples", article_prompt)
        self.assertTrue(draft.page_notes[0].startswith("Seasonal costume"))

    def test_regenerate_keeps_links_and_replaces_the_article(self):
        self.ready()
        draft = self.make_draft()
        self.gem.replies += [reply("Another title"), reply("Another title")]
        self.wf.regenerate(draft)
        self.assertEqual(draft.title, "Another title")
        self.assertEqual([l.anchor for l in draft.links], ["great deals", "buying guide"])

    def test_gemini_failure_is_reported(self):
        self.ready()
        analysis = None
        self.gem.replies += [DETECT, DETECT, ANCHORS, GeminiError("a"), GeminiError("b"), GeminiError("c")]
        analysis = self.wf.analyze(list(URLS), "\n".join(KEYWORDS))
        with self.assertRaises(GeminiError):
            self.wf.generate(analysis, "desks", "India", [])


# Tests for editing and posting
class ReviewAndPostTests(WorkflowBase):
    def setUp(self):
        super().setUp()
        self.ready()
        self.draft = self.make_draft()

    def test_recheck_unchanged_text_passes(self):
        _, report = self.wf.recheck(self.draft, self.draft.title, self.draft.text)
        self.assertTrue(report.passed, report.problems)

    def test_recheck_finds_problems_after_edits(self):
        text = self.draft.text.replace("great deals", "bargains")  # removes the keyword and its link
        html_text, report = self.wf.recheck(self.draft, self.draft.title, text)
        self.assertFalse(report.passed)
        self.assertTrue(any("great deals" in p for p in report.problems))
        self.assertEqual(html_text.count("<a "), 1)

    def test_change_anchor(self):
        text = self.draft.text
        new = self.wf.change_anchor(self.draft, text, 0, "Home Office")
        self.assertEqual(self.draft.links[0].anchor, "home office")
        self.assertIn("[home office]", new)
        self.assertNotIn("[great deals]", new)
        self.assertIn("great deals", new)  # still in the text, no longer a link
        _, report = self.wf.recheck(self.draft, self.draft.title, new)
        self.assertTrue(report.passed, report.problems)

    def test_change_anchor_errors_leave_everything_unchanged(self):
        before = (self.draft.text, [l.anchor for l in self.draft.links])
        for keyword in ("not a keyword", "buying guide"):  # unknown, and used by the other link
            with self.assertRaises(ValidationError):
                self.wf.change_anchor(self.draft, self.draft.text, 0, keyword)
        no_keyword = self.draft.text.replace("home office", "x1").replace("Home office", "x1")
        with self.assertRaises(ValidationError):
            self.wf.change_anchor(self.draft, no_keyword, 0, "home office")
        self.assertEqual((self.draft.text, [l.anchor for l in self.draft.links]), before)

    def test_no_warnings_for_a_good_first_post(self):
        self.assertEqual(self.wf.warnings_before_post(self.draft, self.draft.title, self.draft.text), [])

    def test_warning_for_problems(self):
        warnings = self.wf.warnings_before_post(self.draft, self.draft.title, self.draft.text.replace("[buying guide]", "x"))
        self.assertEqual(len(warnings), 1)
        self.assertIn("check problem", warnings[0])

    def test_post_needs_confirmation_blog_title_and_text(self):
        with self.assertRaises(ValidationError):
            self.wf.post(self.draft, self.draft.title, self.draft.text, live=False, confirmed=False)
        with self.assertRaises(ValidationError):
            self.wf.post(self.draft, " ", self.draft.text, live=False, confirmed=True)
        with self.assertRaises(ValidationError):
            self.wf.post(self.draft, self.draft.title, "  ", live=False, confirmed=True)
        self.wf.select_blog("")
        with self.assertRaises(ConfigError):
            self.wf.post(self.draft, self.draft.title, self.draft.text, live=False, confirmed=True)
        self.assertEqual(self.blogger.posts, [])

    def test_post_as_draft_uses_the_edited_text(self):
        text = self.draft.text.replace("## First part", "## My own heading")
        result = self.wf.post(self.draft, "My title", text, live=False, confirmed=True)
        sent = self.blogger.posts[0]
        self.assertEqual((sent["blog_id"], sent["title"], sent["draft"]), ("111", "My title", True))
        self.assertIn("<h2>My own heading</h2>", sent["html"])
        self.assertEqual(sent["html"].count("<a "), 2)
        self.assertEqual((result.url, result.status, result.live), ("https://my.blogspot.com/p.html", "DRAFT", False))

    def test_post_live(self):
        result = self.wf.post(self.draft, self.draft.title, self.draft.text, live=True, confirmed=True)
        self.assertFalse(self.blogger.posts[0]["draft"])
        self.assertTrue(result.live)

    def test_repeat_warning_after_a_post(self):
        self.wf.post(self.draft, self.draft.title, self.draft.text, live=False, confirmed=True)
        self.clock += 3600
        warnings = self.wf.warnings_before_post(self.draft, self.draft.title, self.draft.text)
        self.assertEqual(len(warnings), 1)
        self.assertIn("already used", warnings[0])

    def test_daily_limit_blocks_live_posts_but_not_drafts(self):
        self.wf.save_settings("KEY", "", "300", "400", "1")
        self.wf.post(self.draft, self.draft.title, self.draft.text, live=True, confirmed=True)
        with self.assertRaises(ValidationError):
            self.wf.post(self.draft, self.draft.title, self.draft.text, live=True, confirmed=True)
        self.wf.post(self.draft, self.draft.title, self.draft.text, live=False, confirmed=True)  # drafts are fine
        self.assertEqual(len(self.blogger.posts), 2)
        self.clock += 86400 + 1  # a day later the limit is free again
        self.wf.post(self.draft, self.draft.title, self.draft.text, live=True, confirmed=True)
        self.assertEqual(len(self.blogger.posts), 3)

    def test_blogger_error_is_raised_and_not_logged(self):
        self.blogger.error = BloggerError("Quota exceeded")
        with self.assertRaises(BloggerError):
            self.wf.post(self.draft, self.draft.title, self.draft.text, live=True, confirmed=True)
        self.assertEqual(self.wf.log.live_posts_last_day("111", self.clock), 0)


if __name__ == "__main__":
    unittest.main()
