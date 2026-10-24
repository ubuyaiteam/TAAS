"""Tests for the fixes made after the first real run on a Windows PC."""

import json  # write JSON
import unittest  # test tools

from taas import pagereader  # the code being tested
from taas.errors import AuthRequiredError, BloggerError, PageReadError  # our error types

from tests import test_auth as ta, test_blogger as tb, test_gemini_pagereader as tg, test_ui_smoke as ts, test_workflow as tw  # test helpers
from tests.helpers import KEYWORDS, URLS, reply  # test helpers


# Blogger 403 errors get a plain-language hint when the cause is known
class BloggerHintTests(unittest.TestCase):
    def message(self, text):
        client, _ = tb.client(tb.FakeResponse(403, {"error": {"message": text}}))
        with self.assertRaises(BloggerError) as ctx:
            client.create_post("1", "T", "<p>x</p>")
        return str(ctx.exception)

    def test_no_permission_names_the_likely_cause(self):
        msg = self.message("The caller does not have permission")
        self.assertIn("The caller does not have permission", msg)  # Blogger's own words are kept
        self.assertIn("owns this blog", msg)
        self.assertIn("Use another Google account", msg)

    def test_missing_scope_says_to_tick_the_box(self):
        self.assertIn("tick the Blogger box", self.message("Request had insufficient authentication scopes."))

    def test_other_403_errors_get_no_wrong_hint(self):
        msg = self.message("Quota exceeded")
        self.assertNotIn("owns this blog", msg)
        self.assertNotIn("tick", msg)


# Sign-in stops at once when the user unticked the Blogger permission on Google's screen
class ScopeTests(unittest.TestCase):
    def sign_in(self, scope):
        body = {"access_token": "a1", "refresh_token": "r1", "expires_in": 3600, "scope": scope}
        http = ta.FakeHttp(ta.FakeResponse(200, body))
        return ta.SignInTests.run_sign_in(self, lambda st: f"code=abc&state={st}", http)

    def test_blogger_permission_missing(self):
        with self.assertRaises(AuthRequiredError) as ctx:
            self.sign_in("openid email")  # nothing is saved; run_sign_in checks that
        self.assertIn("Blogger", str(ctx.exception))

    def test_blogger_permission_given(self):
        token, stored = self.sign_in("openid https://www.googleapis.com/auth/blogger")
        self.assertEqual(stored["refresh_token"], "r1")


# A website that blocks tools: the message tells the owner how to allow us
class BlockedPageTests(unittest.TestCase):
    def test_403_message_names_the_reader(self):
        with self.assertRaises(PageReadError) as ctx:
            pagereader.fetch_page("https://a.com", tg.FakeWeb(tg.Resp(403)))
        self.assertIn("TAAS-reader", str(ctx.exception))
        self.assertIn("HTTP 403", str(ctx.exception))

    def test_the_reader_introduces_itself_honestly(self):
        web = tg.FakeWeb(tg.Resp(200, text="<html>ok</html>"))
        pagereader.fetch_page("https://a.com", web)
        self.assertIn("TAAS-reader", web.calls[0][1]["headers"]["User-Agent"])


# The user's own note replaces the page text when a page cannot be read
class NoteTests(tw.WorkflowBase):
    NOTE = "Halloween costume deals for couples"

    def test_note_reaches_the_anchor_choice_and_the_article(self):
        self.ready()

        def reader(url, http):
            if url == URLS[0]:
                raise PageReadError("blocked (HTTP 403).")
            return tw.fake_reader(url, http)

        self.wf.reader = reader
        self.gem.replies += [tw.DETECT]  # only the readable page is sent to Gemini
        analysis = self.wf.analyze(list(URLS), "\n".join(KEYWORDS))
        self.assertIn("by hand", analysis.analyses[0].detection.error)
        analysis.analyses[0].detection.note = self.NOTE
        self.gem.replies += [tw.ANCHORS, reply(), reply()]
        self.wf.generate(analysis, "costumes", "Australia", [])
        anchors_prompt, article_prompt = self.gem.calls[-3]["prompt"], self.gem.calls[-2]["prompt"]
        self.assertIn(self.NOTE, anchors_prompt)
        self.assertIn(self.NOTE, article_prompt)

    def test_note_wins_over_a_readable_page(self):
        item = type("Item", (), {})()
        item.url, item.detection = URLS[0], type("D", (), {"note": "My own words"})()
        item.page = tw.fake_reader(URLS[0], None)
        self.assertEqual(self.wf._page_with_note(item).description, "My own words")
        self.assertEqual(self.wf._page_with_note(item).title, "Desks")  # the rest of the page is kept


# The note boxes on the Details screen
class NoteScreenTests(ts.UiBase):
    def test_note_typed_on_screen_is_used(self):
        self.do_setup()
        s = self.app.screen
        self.click("+ Add another URL")
        s.urls[0].insert(0, URLS[0])
        s.urls[1].insert(0, URLS[1])
        s.keywords.insert("1.0", "\n".join(KEYWORDS))
        self.gem.replies += [tw.DETECT, tw.DETECT]
        self.click("Read my pages")
        d = self.app.screen
        self.assertEqual(len(d.notes), 2)
        d.notes[0].insert(0, "Costume deals page")
        self.gem.replies += [tw.ANCHORS, reply(), reply()]
        self.click("Write the article")
        self.assertIn("Costume deals page", self.gem.calls[-2]["prompt"])


if __name__ == "__main__":
    unittest.main()
