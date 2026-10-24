"""Tests for pictures in articles, and for the version label and update notice on screen."""

import unittest  # test tools
from unittest import mock  # replace a value during one test
from taas import updates  # the update settings
from tests.test_ui_smoke import UiBase, find, labels, pump, ui  # the screen test setup (also loads the stand-in toolkit)
from tests.helpers import sample_links  # sample links
from taas.article import Link  # one link
from taas.checks import run_checks  # automatic checks
from taas.editor import html_to_text, make_image_line, text_to_html  # editable text
from taas.errors import UpdateError, ValidationError  # our error types
from taas.updates import UpdateInfo  # what an update check returns

PIC = "https://pics.example.com/desk.jpg"


class ImageLineTests(unittest.TestCase):
    def test_line_is_made_and_cleaned(self):
        self.assertEqual(make_image_line(f" {PIC} ", "A tidy\n desk | setup {x}"), f"{{image: {PIC} | A tidy desk setup x}}")

    def test_bad_addresses_are_refused(self):
        for bad in ("", "desk.jpg", "ftp://x.example/a.jpg", "https://x.example/a b.jpg", "https://x.example/a|b.jpg", "https://x.example/{a}.jpg"):
            with self.assertRaises(ValidationError, msg=bad):
                make_image_line(bad, "alt")

    def test_description_is_optional(self):
        self.assertEqual(make_image_line(PIC), f"{{image: {PIC} | }}")


class ImageHtmlTests(unittest.TestCase):
    links = sample_links()

    def convert(self, text):
        return text_to_html(text, self.links)

    def test_picture_line_becomes_an_image(self):
        html, notes = self.convert(f"Text with [great deals] and [buying guide].\n\n{{image: {PIC} | A desk}}")
        self.assertIn(f'<img src="{PIC}" alt="A desk"', html)
        self.assertEqual(notes, [])

    def test_picture_directly_under_a_paragraph_is_still_its_own_block(self):
        html, _ = self.convert(f"First line [great deals] [buying guide]\n{{image: {PIC} | A desk}}\nNext paragraph")
        self.assertEqual(html.count("<p"), 3)
        self.assertIn("<p>Next paragraph</p>", html)

    def test_special_characters_are_made_safe(self):
        html, _ = self.convert('[great deals] [buying guide]\n\n{image: https://x.example/a.jpg?a=1&b=2 | He said "hi" <b>}')
        self.assertIn("a=1&amp;b=2", html)
        self.assertIn("&quot;hi&quot; &lt;b&gt;", html)
        self.assertNotIn("<b>", html)

    def test_missing_description_gives_a_note_but_still_adds_the_picture(self):
        html, notes = self.convert(f"[great deals] [buying guide]\n\n{{image: {PIC}}}")
        self.assertIn("<img", html)
        self.assertTrue(any("no description" in n for n in notes))

    def test_unusable_address_is_left_out_with_a_note(self):
        html, notes = self.convert("[great deals] [buying guide]\n\n{image: javascript:alert(1) | x}\n\n{image: nothing | y}")
        self.assertNotIn("<img", html)
        self.assertNotIn("javascript", html)
        self.assertEqual(len([n for n in notes if "left out" in n]), 2)

    def test_pictures_do_not_change_links_words_or_keywords(self):
        words = " ".join(["word"] * 5)
        base = f"## A\n\n[great deals] [buying guide] {words}\n\n## B\n\nhome office desk setup budget tips"
        with_picture = base + f"\n\n{{image: {PIC} | home office desk}}"
        keywords = ["great deals", "home office", "desk setup", "budget tips", "buying guide"]
        report = lambda text: run_checks(self.convert(text)[0], "T", keywords, self.links, [], 1, 1000)
        a, b = report(base), report(with_picture)
        self.assertEqual((a.words, a.problems), (b.words, b.problems))

    def test_brand_names_may_not_appear_in_a_picture_description(self):
        html, _ = self.convert(f"## A\n\n[great deals] [buying guide]\n\n{{image: {PIC} | Acme desk}}")
        report = run_checks(html, "T", [], self.links, ["Acme"], 1, 1000)
        self.assertTrue(any("picture description" in p for p in report.problems))

    def test_the_picture_address_may_hold_a_brand_like_a_link_address_may(self):
        html, _ = self.convert(f"## A\n\n[great deals] [buying guide]\n\n{{image: https://acme.example/a.jpg | A desk}}")
        report = run_checks(html, "T", [], self.links, ["Acme"], 1, 1000)
        self.assertFalse(any("Acme" in p for p in report.problems))

    def test_html_back_to_text_keeps_the_picture(self):
        html, _ = self.convert(f"[great deals] [buying guide]\n\n{{image: {PIC} | A desk}}")
        self.assertIn(f"{{image: {PIC} | A desk}}", html_to_text(html))


class ArticleScreenImageTests(UiBase):
    def setUp(self):
        super().setUp()
        self.do_setup()
        self.to_article()
        self.screen = self.app.screen

    def test_add_image_puts_a_line_in_the_text(self):
        self.screen.image_url.insert(0, PIC)
        self.screen.image_alt.insert(0, "A tidy desk")
        self.click("Add image")
        self.assertIn(f"{{image: {PIC} | A tidy desk}}", self.screen.body.get("1.0", "end"))
        self.assertEqual(self.screen.image_url.get(), "")  # boxes are cleared for the next one
        self.assertIn("Image added to the article text.", labels(self.app))

    def test_bad_address_shows_an_error_and_changes_nothing(self):
        before = self.screen.body.get("1.0", "end")
        self.screen.image_url.insert(0, "not an address")
        self.click("Add image")
        self.assertEqual(self.screen.body.get("1.0", "end"), before)
        self.assertTrue(any("web address" in t for t in labels(self.app)))

    def test_generate_button_is_there_but_cannot_be_clicked(self):
        button = find(self.app, "CTkButton", "Generate images automatically (coming soon)")
        self.assertEqual(button.kw["state"], "disabled")
        self.assertIsNone(button.kw.get("command"))

    def test_picture_reaches_blogger(self):
        self.screen.image_url.insert(0, PIC)
        self.screen.image_alt.insert(0, "A tidy desk")
        self.click("Add image")
        self.screen.confirm.click()
        find(self.app, "CTkButton", "Post to Blogger").invoke()
        pump(self.app)
        html = self.blogger.posts[0]["html"]
        self.assertIn(f'<img src="{PIC}" alt="A tidy desk"', html)
        self.assertEqual(html.count("<a "), 2)

    def test_picture_without_description_makes_posting_ask_first(self):
        self.screen.image_url.insert(0, PIC)
        self.click("Add image")
        self.assertTrue(any("no description" in t for t in labels(self.app)))  # shown in the checks
        self.screen.confirm.click()
        self.answer = False
        find(self.app, "CTkButton", "Post to Blogger").invoke()
        pump(self.app)
        self.assertIn("Before posting", self.questions[-1][0])
        self.assertEqual(self.blogger.posts, [])


class UpdateScreenTests(UiBase):
    def setUp(self):
        super().setUp()
        self.infos = []
        self.opened = []
        self.shown = []
        self.wf._update_check = lambda current, repo, token="": self.next_result(current, repo)
        self.wf.open_browser = self.opened.append
        self.wf.settings.update_repo = "o/r"
        self.result = UpdateInfo("1.1.0", "1.3.0", "https://github.com/o/r/releases/tag/v1.3.0", "Pictures in articles", True)

    def next_result(self, current, repo):
        self.infos.append((current, repo))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result

    def new_app(self, auto_check):
        app = ui.App(self.wf, auto_check=auto_check)
        app.show_info = lambda title, message: self.shown.append((title, message))
        self.app = app
        return app

    def test_version_is_shown(self):
        self.new_app(False)
        self.assertIn(f"Version {self.wf.version}", labels(self.app))
        self.assertIn(f"v{self.wf.version}", self.app.titles[-1])

    def test_no_check_without_auto_check(self):
        self.new_app(False)
        pump(self.app)
        self.assertEqual(self.infos, [])

    def test_start_up_check_shows_the_notice_quietly(self):
        self.new_app(True)
        pump(self.app)
        self.assertEqual(self.infos, [(self.wf.version, "o/r")])
        self.assertIn("New version 1.3.0 is available (you have 1.1.0).", labels(self.app))
        self.assertEqual(self.shown, [])  # no pop-up, and nothing blocked
        self.assertFalse(self.app.busy)
        find(self.app, "CTkButton", "Open download page").invoke()
        self.assertEqual(self.opened, [self.result.url])

    def test_start_up_check_stays_silent_when_up_to_date_or_failing(self):
        for result in (UpdateInfo("1.1.0", "1.1.0", "u", "", False), UpdateError("no")):
            self.result = result
            self.new_app(True)
            pump(self.app)
            self.assertFalse(any("New version" in t for t in labels(self.app)))
            self.assertEqual(self.shown, [])

    def test_start_up_check_is_skipped_when_no_repository_is_known(self):
        self.wf.settings.update_repo = ""
        # the real repository name is set now, so pretend it is not for this test
        with mock.patch.object(updates, "DEFAULT_REPO", ""):
            self.new_app(True)
            pump(self.app)
        self.assertEqual(self.infos, [])

    def test_button_reports_a_new_version(self):
        self.new_app(False)
        self.click("Check for updates")
        self.assertEqual(len(self.shown), 1)
        self.assertIn("1.3.0", self.shown[0][1])
        self.assertIn("Pictures in articles", self.shown[0][1])
        self.assertIn("New version 1.3.0 is available (you have 1.1.0).", labels(self.app))

    def test_button_reports_up_to_date(self):
        self.result = UpdateInfo("1.1.0", "1.1.0", "u", "", False)
        self.new_app(False)
        self.click("Check for updates")
        self.assertIn("latest version", self.shown[0][1])

    def test_button_reports_a_problem_in_plain_words(self):
        self.result = UpdateError("GitHub found no published release.")
        self.new_app(False)
        self.click("Check for updates")
        self.assertEqual(self.shown[0][1], "GitHub found no published release.")


if __name__ == "__main__":
    unittest.main()
