"""Smoke test for the screens: drives the whole app through its buttons with a stand-in toolkit.

This checks the screen code and the flow between screens. It cannot check how the windows look.
"""

import json  # write JSON
import sys  # replace a module
import time  # wait for background jobs
import unittest  # test tools

from tests import stub_ctk, test_workflow as tw  # the stand-in toolkit and the workflow test setup
from tests.helpers import KEYWORDS, URLS, reply  # test helpers

sys.modules["customtkinter"] = stub_ctk  # the app now uses the stand-in
from taas.errors import BloggerError  # our error types
from taas.ui import app as ui  # the screens being tested


# Find a widget of a type by its text
def find(root, kind, text):
    for widget in root.descendants():
        if type(widget).__name__ == kind and widget.kw.get("text") == text:
            return widget
    raise AssertionError(f"No {kind} with text {text!r} on screen")


# All label texts on screen (for reading messages)
def labels(root):
    return [w.kw.get("text", "") for w in root.descendants() if type(w).__name__ == "CTkLabel"]


# Let background jobs finish and run the window's waiting callbacks
def pump(app, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        if not app.afters and not app.busy:
            return
        callbacks, app.afters[:] = app.afters[:], []
        for callback in callbacks:
            callback()
        if app.busy:
            time.sleep(0.01)
    raise AssertionError("A background job did not finish")


class UiBase(tw.WorkflowBase):
    def setUp(self):
        super().setUp()
        (self.home / "client_secret.json").write_text(json.dumps({"installed": {"client_id": "cid", "client_secret": "s"}}))
        # a fake sign-in that saves a token, like the real one
        self.wf._sign_in = lambda client, store, open_browser=None: store.save({"access_token": "a", "refresh_token": "r"})
        self.questions = []
        self.answer = True
        self.app = ui.App(self.wf)
        self.app.ask_yes_no = lambda title, message: (self.questions.append((title, message)), self.answer)[1]

    def click(self, text):
        find(self.app, "CTkButton", text).invoke()
        pump(self.app)

    def screen_name(self):
        return type(self.app.screen).__name__

    # Do Setup through the screen
    def do_setup(self):
        s = self.app.screen
        s.key.insert(0, "KEY")
        self.click("Sign in with Google")  # signs in, then loads the blogs and picks the only blog
        self.click("Continue")

    # Go from Input to the Article screen
    def to_article(self):
        s = self.app.screen
        self.click("+ Add another URL")
        s.urls[0].insert(0, URLS[0])
        s.urls[1].insert(0, URLS[1])
        s.keywords.insert("1.0", "\n".join(KEYWORDS))
        self.gem.replies += [tw.DETECT, tw.DETECT]
        self.click("Read my pages")
        self.assertEqual(self.screen_name(), "DetailsScreen")
        self.gem.replies += [tw.ANCHORS, reply(), reply()]
        self.click("Write the article")
        self.assertEqual(self.screen_name(), "ArticleScreen")


class SetupFlowTests(UiBase):
    def test_starts_on_setup_and_continues_after_sign_in(self):
        self.assertEqual(self.screen_name(), "SetupScreen")
        self.assertIn("Not signed in", " ".join(labels(self.app)))
        self.do_setup()
        self.assertEqual(self.screen_name(), "InputScreen")
        self.assertEqual(self.wf.settings.blog_id, "111")
        self.assertEqual(self.wf.settings.gemini_api_key, "KEY")

    def test_blog_selector_uses_themed_dropdown(self):
        selector = self.app.screen.blog_menu
        self.assertEqual(type(selector).__name__, "CTkOptionMenu")
        self.assertEqual(selector.cget("fg_color"), ui.FIELD_BG)
        self.assertEqual(selector.cget("button_color"), ui.ACCENT)
        self.assertEqual(selector.cget("dropdown_hover_color"), ui.ACCENT_SOFT)

    def test_provider_dropdown_saves_openai_credentials(self):
        screen = self.app.screen
        screen.openai_provider_button.invoke()
        screen.openai_key.insert(0, "OPENAI-KEY")
        screen.openai_model.delete(0, "end")
        screen.openai_model.insert(0, "gpt-custom")
        self.click("Save settings")
        self.assertEqual(self.wf.settings.ai_provider, "openai")
        self.assertEqual(self.wf.settings.openai_api_key, "OPENAI-KEY")
        self.assertEqual(self.wf.settings.openai_model, "gpt-custom")
        self.assertIn("OpenAI API key", " ".join(labels(self.app)))

    def test_provider_selector_is_a_segmented_control_and_switches_credentials(self):
        screen = self.app.screen
        self.assertEqual(type(screen.provider_selector).__name__, "CTkFrame")
        self.assertEqual(screen.gemini_provider_button.cget("text_color"), (ui.INK[0], "#FFFFFF"))
        self.assertEqual(screen.openai_provider_button.cget("text_color"), (ui.INK[0], "#FFFFFF"))
        self.assertEqual(screen.gemini_provider_button.cget("fg_color"), ui.ACCENT)
        self.assertEqual(screen.openai_provider_button.cget("fg_color"), ui.FIELD_BG)
        screen.openai_provider_button.invoke()
        self.assertEqual(screen.openai_provider_button.cget("text_color"), (ui.INK[0], "#FFFFFF"))
        self.assertEqual(screen.gemini_provider_button.cget("text_color"), (ui.INK[0], "#FFFFFF"))
        self.assertEqual(screen.openai_provider_button.cget("fg_color"), ui.ACCENT)
        self.assertEqual(screen.gemini_provider_button.cget("fg_color"), ui.FIELD_BG)
        self.assertEqual(screen.openai_fields.master, screen.page)
        screen.gemini_provider_button.invoke()
        self.assertEqual(screen.gemini_provider_button.cget("text_color"), (ui.INK[0], "#FFFFFF"))
        self.assertEqual(screen.openai_provider_button.cget("text_color"), (ui.INK[0], "#FFFFFF"))
        self.assertEqual(screen.gemini_provider_button.cget("fg_color"), ui.ACCENT)
        self.assertEqual(screen.openai_provider_button.cget("fg_color"), ui.FIELD_BG)
        self.assertEqual(screen.gemini_fields.master, screen.page)
        self.assertIs(screen.gemini_fields.pack_options["before"], screen.min_words_label)

    def test_continue_lists_what_is_missing(self):
        self.click("Continue")
        self.assertEqual(self.screen_name(), "SetupScreen")
        text = " ".join(labels(self.app))
        for part in ("Gemini API key", "Sign in with Google", "Choose your Blogger blog"):
            self.assertIn(part, text)

    def test_bad_setting_shows_an_error(self):
        s = self.app.screen
        s.min_words.delete(0, "end")
        s.min_words.insert(0, "abc")
        self.click("Save settings")
        self.assertIn("whole number", " ".join(labels(self.app)))

    def test_missing_client_file_is_explained(self):
        (self.home / "client_secret.json").unlink()
        self.app.show(ui.SetupScreen)
        self.assertIn("client_secret.json", " ".join(labels(self.app)))

    def test_switch_account_signs_out_then_in(self):
        self.do_setup()
        self.app.open_setup()
        self.click("Use another Google account")
        self.assertTrue(self.wf.is_signed_in())


class WholeFlowTests(UiBase):
    def setUp(self):
        super().setUp()
        self.do_setup()

    def test_input_errors_stay_on_the_input_screen(self):
        s = self.app.screen
        s.urls[0].insert(0, "not a web address")
        self.click("Read my pages")
        self.assertEqual(self.screen_name(), "InputScreen")
        self.assertTrue(any("web address" in t for t in labels(self.app)))

    def test_url_fields_are_added_on_demand_up_to_the_limit(self):
        s = self.app.screen
        self.assertEqual(len(s.urls), 1)
        self.click("+ Add another URL")
        self.assertEqual(len(s.urls), 2)
        self.click("+ Add another URL")
        self.assertEqual(len(s.urls), 3)
        self.assertEqual(s.add_url_button.kw["state"], "disabled")
        self.assertEqual(s.add_url_button.kw["text"], f"Maximum of {ui.MAX_URLS} URLs added")
        s.on_add_url()
        self.assertEqual(len(s.urls), 3)

    def test_details_are_prefilled_and_editable(self):
        s = self.app.screen
        self.click("+ Add another URL")
        s.urls[0].insert(0, URLS[0])
        s.urls[1].insert(0, URLS[1])
        s.keywords.insert("1.0", ", ".join(KEYWORDS))
        self.gem.replies += [tw.DETECT, tw.DETECT]
        self.click("Read my pages")
        d = self.app.screen
        self.assertEqual([e.get() for e in d.brands], ["Acme", "Acme"])
        self.assertEqual((d.category.get(), d.country.get()), ("office furniture", "India"))
        d.country.delete(0, "end")
        self.click("Write the article")  # empty country is refused
        self.assertEqual(self.screen_name(), "DetailsScreen")
        self.assertTrue(any("country" in t.lower() for t in labels(self.app)))

    def test_corrections_survive_going_back_and_forth(self):
        self.to_article()
        self.click("Back")  # article -> details
        d = self.app.screen
        d.country.delete(0, "end")
        d.country.insert(0, "Canada")
        d.brands[0].delete(0, "end")
        d.brands[0].insert(0, "Globex")
        self.click("Back")  # details -> input
        self.assertEqual(self.app.analysis.country, "Canada")
        self.assertEqual(self.app.analysis.analyses[0].detection.brand, "Globex")
        self.gem.replies += [tw.DETECT, tw.DETECT]
        self.click("Read my pages")  # reads again, so the detection starts fresh
        self.assertEqual(self.screen_name(), "DetailsScreen")

    def test_note_boxes_exist_keep_their_text_and_reach_the_article_prompt(self):
        s = self.app.screen
        self.click("+ Add another URL")
        s.urls[0].insert(0, URLS[0])
        s.urls[1].insert(0, URLS[1])
        s.keywords.insert("1.0", ", ".join(KEYWORDS))
        self.gem.replies += [tw.DETECT, tw.DETECT]
        self.click("Read my pages")
        d = self.app.screen
        self.assertEqual(len(d.notes), 2)
        d.notes[0].insert(0, "Costume offers page")
        self.click("Back")
        self.assertEqual(self.app.analysis.analyses[0].detection.note, "Costume offers page")
        self.gem.replies += [tw.DETECT, tw.DETECT]
        self.click("Read my pages")  # reading again starts fresh
        self.assertEqual(self.app.screen.notes[0].get(), "")

    def test_back_from_the_article_keeps_the_edited_text(self):
        self.to_article()
        a = self.app.screen
        a.body.delete("1.0", "end")
        a.body.insert("1.0", "My edited text")
        self.click("Back")
        self.assertEqual(self.app.draft.text, "My edited text")

    def test_back_button_keeps_what_was_typed(self):
        s = self.app.screen
        self.click("+ Add another URL")
        s.urls[0].insert(0, URLS[0])
        s.urls[1].insert(0, URLS[1])
        s.keywords.insert("1.0", ", ".join(KEYWORDS))
        self.gem.replies += [tw.DETECT, tw.DETECT]
        self.click("Read my pages")
        self.click("Back")
        self.assertEqual(self.app.screen.urls[0].get(), URLS[0])
        self.assertEqual(self.app.screen.urls[1].get(), URLS[1])

    def test_write_edit_and_post_a_draft(self):
        self.to_article()
        a = self.app.screen
        self.assertIn("[great deals]", a.body.get("1.0", "end"))
        self.assertEqual(a.menus[0].get(), "great deals")
        self.assertIn("All checks passed", " ".join(labels(self.app)))
        post = find(self.app, "CTkButton", "Post to Blogger")
        self.assertEqual(post.kw["state"], "disabled")  # not until the box is ticked
        a.confirm.click()
        self.assertEqual(post.kw["state"], "normal")
        a.title_entry.delete(0, "end")
        a.title_entry.insert(0, "My own title")
        a.mode.set(ui.DRAFT_CHOICE)
        post.invoke()
        pump(self.app)
        self.assertEqual(self.screen_name(), "ResultScreen")
        self.assertIn("Saved as a Blogger draft.", labels(self.app))
        sent = self.blogger.posts[0]
        self.assertEqual((sent["title"], sent["draft"]), ("My own title", True))
        self.assertEqual(sent["html"].count("<a "), 2)
        self.assertEqual(self.questions, [])  # no warnings, no live question

    def test_live_post_asks_first(self):
        self.to_article()
        a = self.app.screen
        a.confirm.click()
        a.mode.set(ui.LIVE_CHOICE)
        self.answer = False
        find(self.app, "CTkButton", "Post to Blogger").invoke()
        pump(self.app)
        self.assertEqual(self.screen_name(), "ArticleScreen")  # said no: nothing posted
        self.assertEqual(self.blogger.posts, [])
        self.assertIn("publishes", self.questions[-1][1])
        self.answer = True
        find(self.app, "CTkButton", "Post to Blogger").invoke()
        pump(self.app)
        self.assertIn("Published on your blog.", labels(self.app))
        self.assertFalse(self.blogger.posts[0]["draft"])

    def test_problems_are_shown_and_posting_asks(self):
        self.to_article()
        a = self.app.screen
        a.body.delete("1.0", "end")
        a.body.insert("1.0", "## Short\n\nToo short.")
        self.click("Check again")
        self.assertTrue(any("Please look at these" in t for t in labels(self.app)))
        a.confirm.click()
        self.answer = False
        find(self.app, "CTkButton", "Post to Blogger").invoke()
        pump(self.app)
        self.assertIn("Before posting", self.questions[-1][0])
        self.assertEqual(self.blogger.posts, [])

    def test_change_the_link_keyword(self):
        self.to_article()
        a = self.app.screen
        self.assertTrue(all(type(menu).__name__ == "CTkOptionMenu" for menu in a.menus))
        self.assertTrue(all(menu.cget("fg_color") == ui.FIELD_BG for menu in a.menus))
        self.assertTrue(all(menu.cget("button_color") == ui.ACCENT for menu in a.menus))
        self.assertTrue(all(menu.cget("dropdown_hover_color") == ui.ACCENT_SOFT for menu in a.menus))
        a.menus[0].choose("home office")
        body = a.body.get("1.0", "end")
        self.assertIn("[home office]", body)
        self.assertNotIn("[great deals]", body)
        self.assertIn("All checks passed", " ".join(labels(self.app)))

    def test_change_the_link_keyword_to_one_that_is_taken(self):
        self.to_article()
        a = self.app.screen
        a.menus[0].choose("buying guide")
        self.assertEqual(a.menus[0].get(), "great deals")  # the old choice is put back
        self.assertTrue(any("already" in t for t in labels(self.app)))

    def test_write_it_again(self):
        self.to_article()
        self.gem.replies += [reply("A brand new title"), reply("A brand new title")]
        self.click("Write it again")
        self.assertEqual(self.app.screen.title_entry.get(), "A brand new title")
        self.answer = False
        self.click("Write it again")  # said no: nothing changes
        self.assertEqual(self.app.screen.title_entry.get(), "A brand new title")

    def test_blogger_error_keeps_the_article(self):
        self.to_article()
        self.blogger.error = BloggerError("Quota exceeded")
        a = self.app.screen
        a.confirm.click()
        find(self.app, "CTkButton", "Post to Blogger").invoke()
        pump(self.app)
        self.assertEqual(self.screen_name(), "ResultScreen")
        self.assertIn("The article was not posted", labels(self.app))
        self.assertTrue(any("Quota exceeded" in t for t in labels(self.app)))
        self.click("Back to the article")
        self.assertEqual(self.screen_name(), "ArticleScreen")
        self.assertIn("[great deals]", self.app.screen.body.get("1.0", "end"))

    def test_result_link_copy_and_new_article(self):
        self.to_article()
        a = self.app.screen
        a.confirm.click()
        find(self.app, "CTkButton", "Post to Blogger").invoke()
        pump(self.app)
        self.click("Copy link")
        self.assertEqual(self.app.clipboard, "https://my.blogspot.com/p.html")
        self.click("Write another article")
        self.assertEqual(self.screen_name(), "InputScreen")
        self.assertEqual(self.app.screen.urls[0].get(), "")

    def test_setup_button_is_ignored_while_busy(self):
        self.app.set_busy("Working...")
        self.app.open_setup()
        self.assertEqual(self.screen_name(), "InputScreen")
        self.app.set_busy("")

    def test_unexpected_crash_is_shown_not_thrown(self):
        def boom():
            raise RuntimeError("boom")
        results = []
        self.app.run_task(boom, lambda kind, value: results.append((kind, value)), "x")
        pump(self.app)
        self.assertEqual(results[0][0], "error")
        self.assertIn("boom", results[0][1])


if __name__ == "__main__":
    unittest.main()
