import json  # write JSON
import tempfile  # temporary folders
import unittest  # test tools
from pathlib import Path  # file paths

from taas import article, editor, safeguards  # the code being tested
from taas.errors import ValidationError  # our error types

from tests.helpers import KEYWORDS, URLS, make_body, sample_links  # test helpers


# Tests for the editable text
class EditorTests(unittest.TestCase):
    def final(self):
        html_text, problems = article.assemble(make_body(), sample_links())
        self.assertEqual(problems, [])
        return html_text

    def test_html_to_text_shape(self):
        text = editor.html_to_text(self.final())
        self.assertIn("## First part", text)
        self.assertIn("[great deals]", text)
        self.assertIn("[buying guide]", text)
        self.assertNotIn("<", text)
        self.assertEqual(len(text.split("\n\n")), 5)  # 3 paragraphs + 2 headings

    def test_round_trip_keeps_the_links(self):
        original = self.final()
        back, notes = editor.text_to_html(editor.html_to_text(original), sample_links())
        self.assertEqual(notes, [])
        self.assertEqual(back, original)

    def test_lists(self):
        text = editor.html_to_text("<p>Intro</p><ul><li>One</li><li>Two</li></ul>")
        self.assertEqual(text, "Intro\n\n- One\n- Two")
        html_text, _ = editor.text_to_html(text, [])
        self.assertEqual(html_text, "<p>Intro</p><ul><li>One</li><li>Two</li></ul>")

    def test_edits_become_html_and_are_escaped(self):
        html_text, _ = editor.text_to_html("## Title <x>\n\nA & B <script>", [])
        self.assertIn("&lt;script&gt;", html_text)
        self.assertIn("&amp;", html_text)
        self.assertNotIn("<script>", html_text)

    def test_missing_link_gives_a_helpful_note(self):
        text = editor.html_to_text(self.final()).replace("[buying guide]", "buying guide")
        html_text, notes = editor.text_to_html(text, sample_links())
        self.assertEqual(html_text.count("<a "), 1)
        self.assertTrue(any("'[buying guide]' is missing" in n or "[buying guide]" in n for n in notes))

    def test_second_bracket_for_same_link_is_plain_text(self):
        text = "A [great deals] and again [great deals]."
        html_text, notes = editor.text_to_html(text, sample_links())
        self.assertEqual(html_text.count("<a "), 1)
        self.assertNotIn("[", html_text)
        self.assertTrue(notes)

    def test_unknown_brackets_lose_the_brackets(self):
        html_text, notes = editor.text_to_html("See [sic] here", [])
        self.assertEqual(html_text, "<p>See sic here</p>")
        self.assertTrue(notes)

    def test_swap_anchor(self):
        text = "Find [great deals] here. Also a home office plan. And a Home Office tip."
        new = editor.swap_anchor(text, "great deals", "home office")
        self.assertEqual(new, "Find great deals here. Also a [home office] plan. And a Home Office tip.")

    def test_swap_ignores_a_keyword_that_is_only_inside_brackets(self):
        # "buying guide" appears only as a link already, so it cannot become a second link
        with self.assertRaises(ValidationError):
            editor.swap_anchor("A [buying guide] and [great deals].", "great deals", "buying guide")

    def test_swap_needs_the_keyword_in_the_text(self):
        with self.assertRaises(ValidationError):
            editor.swap_anchor("Only [great deals] here", "great deals", "desk setup")


# Tests for the posting limit and repeat warning
class SafeguardTests(unittest.TestCase):
    def log(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        return safeguards.PostLog(Path(d.name) / "post_log.json")

    def test_empty_log(self):
        log = self.log()
        self.assertEqual(log.live_posts_last_day("b1", 1000), 0)
        self.assertIsNone(log.repeat_warning(URLS, 1000))
        log.check_limit(1, "b1", 1000)  # fine

    def test_limit_counts_live_posts_of_this_blog_in_24_hours(self):
        log = self.log()
        now = 10 * safeguards.DAY
        log.record("b1", URLS, True, now - 100)
        log.record("b1", URLS, False, now - 50)  # a draft does not count
        log.record("b2", URLS, True, now - 50)  # another blog does not count
        log.record("b1", URLS, True, now - safeguards.DAY - 1)  # too old
        self.assertEqual(log.live_posts_last_day("b1", now), 1)
        with self.assertRaises(ValidationError):
            log.check_limit(1, "b1", now)
        log.check_limit(2, "b1", now)
        log.check_limit(None, "b1", now)

    def test_repeat_warning_ignores_order_case_and_slash(self):
        log = self.log()
        log.record("b1", URLS, False, 5 * safeguards.DAY)
        later = 6 * safeguards.DAY
        self.assertIsNotNone(log.repeat_warning([URLS[1].upper() + "/", URLS[0]], later))
        self.assertIsNone(log.repeat_warning([URLS[0]], later))  # different set
        self.assertIsNone(log.repeat_warning(URLS, 5 * safeguards.DAY + 8 * safeguards.DAY))  # too long ago

    def test_log_keeps_no_article_text_and_prunes_old_entries(self):
        log = self.log()
        log.record("b1", URLS, True, 1000)
        log.record("b1", URLS, True, 1000 + 40 * safeguards.DAY)
        saved = json.loads(log.path.read_text())
        self.assertEqual(len(saved), 1)
        self.assertEqual(set(saved[0]), {"time", "blog_id", "urls", "live"})

    def test_broken_log_file_counts_as_empty(self):
        log = self.log()
        log.path.write_text("garbage")
        self.assertEqual(log.live_posts_last_day("b1", 1000), 0)
        log.record("b1", URLS, True, 1000)  # and it can be written again
        self.assertEqual(log.live_posts_last_day("b1", 1001), 1)


if __name__ == "__main__":
    unittest.main()
