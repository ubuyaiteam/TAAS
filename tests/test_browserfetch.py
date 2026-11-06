"""Tests for the browser fallback (Playwright is replaced by a fake; no browser is opened)."""

import sys  # replace a library during one test
import tempfile  # a temporary folder
import types  # build a fake library
import unittest  # test tools
from pathlib import Path  # file paths
from unittest import mock  # replace a value during one test

from taas import browserfetch, pagereader  # the code being tested
from taas.errors import PageBlockedError, PageReadError  # our error types
from tests.test_gemini_pagereader import FakeWeb, PAGE, Resp  # fake web answers and a sample page

HTML = "<html><head><title>Real page</title></head><body><p>" + "Good desks. " * 30 + "</p></body></html>"


class FakePWError(Exception):
    pass


class FakePWTimeout(FakePWError):
    pass


# A stand-in for playwright.sync_api. `installed` = browsers that can be launched; `status` = the page's answer.
def fake_playwright(installed=("chrome",), status=200, goto_error=None, settle_error=None, html=HTML):
    state = {"launched": [], "closed": 0, "headless": None}

    class Page:
        def goto(self, url, wait_until=None, timeout=None):
            if goto_error:
                raise goto_error
            return types.SimpleNamespace(status=status)

        def wait_for_load_state(self, name, timeout=None):
            if settle_error:
                raise settle_error

        def content(self):
            return html

    class Browser:
        def new_page(self):
            return Page()

        def close(self):
            state["closed"] += 1

    class Chromium:
        def launch(self, channel=None, headless=None):
            state["launched"].append(channel)
            state["headless"] = headless
            if channel not in installed:
                raise FakePWError(f"Chromium distribution '{channel}' is not found")
            return Browser()

    class Context:
        chromium = Chromium()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    api = types.ModuleType("playwright.sync_api")
    api.sync_playwright = lambda: Context()
    api.Error = FakePWError
    api.TimeoutError = FakePWTimeout
    package = types.ModuleType("playwright")
    package.sync_api = api
    return {"playwright": package, "playwright.sync_api": api}, state


class BrowserFetchTests(unittest.TestCase):
    def run_fetch(self, visible=False, **kw):
        modules, state = fake_playwright(**kw)
        with mock.patch.dict(sys.modules, modules), \
                mock.patch.object(browserfetch, "browser_is_visible", return_value=visible):
            return browserfetch.fetch_html("https://a.com"), state

    def test_returns_the_page_html_from_a_hidden_chrome(self):
        html, state = self.run_fetch()
        self.assertEqual(html, HTML)
        self.assertEqual(state["launched"], ["chrome"])
        self.assertTrue(state["headless"])
        self.assertEqual(state["closed"], 1)

    def test_visible_setting_opens_a_visible_window(self):
        _, state = self.run_fetch(visible=True)
        self.assertFalse(state["headless"])

    def test_uses_edge_when_chrome_is_missing(self):
        _, state = self.run_fetch(installed=("msedge",))
        self.assertEqual(state["launched"], ["chrome", "msedge"])

    def test_no_browser_installed(self):
        with self.assertRaises(PageReadError) as ctx:
            self.run_fetch(installed=())
        self.assertIn("Chrome or Microsoft Edge", str(ctx.exception))

    def test_blocked_in_the_browser_too(self):
        with self.assertRaises(PageReadError) as ctx:
            self.run_fetch(status=403)
        self.assertIn("HTTP 403", str(ctx.exception))

    def test_other_error_status(self):
        with self.assertRaises(PageReadError) as ctx:
            self.run_fetch(status=500)
        self.assertIn("HTTP 500", str(ctx.exception))

    def test_slow_page_that_never_settles_is_still_read(self):
        html, _ = self.run_fetch(settle_error=FakePWTimeout("idle"))
        self.assertEqual(html, HTML)

    def test_page_that_never_opens(self):
        with self.assertRaises(PageReadError) as ctx:
            self.run_fetch(goto_error=FakePWTimeout("Timeout 30000ms exceeded"))
        self.assertIn("too long", str(ctx.exception))

    def test_browser_error_becomes_a_plain_message_and_the_browser_is_closed(self):
        modules, state = fake_playwright(goto_error=FakePWError("net::ERR_NAME_NOT_RESOLVED\nlog line"))
        with mock.patch.dict(sys.modules, modules), mock.patch.object(browserfetch, "browser_is_visible", return_value=False):
            with self.assertRaises(PageReadError) as ctx:
                browserfetch.fetch_html("https://a.com")
        self.assertIn("ERR_NAME_NOT_RESOLVED", str(ctx.exception))
        self.assertNotIn("log line", str(ctx.exception))
        self.assertEqual(state["closed"], 1)

    def test_playwright_not_installed(self):
        with mock.patch.dict(sys.modules, {"playwright": None, "playwright.sync_api": None}), \
                mock.patch.object(browserfetch, "browser_is_visible", return_value=False):
            with self.assertRaises(PageReadError) as ctx:
                browserfetch.fetch_html("https://a.com")
        self.assertIn("not installed", str(ctx.exception))


class VisibleSettingTests(unittest.TestCase):
    def read(self, env_text):
        folder = Path(tempfile.mkdtemp())
        if env_text is not None:
            (folder / ".env").write_text(env_text)
        with mock.patch("taas.config.app_folder", return_value=folder):
            return browserfetch.browser_is_visible()

    def test_off_by_default(self):
        self.assertFalse(self.read(None))
        self.assertFalse(self.read("GEMINI_API_KEY=x\n"))
        self.assertFalse(self.read("BROWSER_VISIBLE=\n"))
        self.assertFalse(self.read("BROWSER_VISIBLE=0\n"))

    def test_on_when_the_env_file_says_so(self):
        for value in ("1", "true", "TRUE", "yes", "on", " 1 "):
            self.assertTrue(self.read(f"BROWSER_VISIBLE={value}\n"), value)


class ReadPageFallbackTests(unittest.TestCase):
    URL = "https://www.acme.in/desks"

    def test_a_blocked_page_is_read_through_the_browser(self):
        calls = []
        page = pagereader.read_page(self.URL, FakeWeb(Resp(403)), browser_fetch=lambda u: calls.append(u) or PAGE)
        self.assertEqual(calls, [self.URL])
        self.assertEqual(page.title, "Desks | Acme")

    def test_all_three_blocking_statuses_use_the_browser(self):
        for status in (401, 403, 429):
            page = pagereader.read_page(self.URL, FakeWeb(Resp(status)), browser_fetch=lambda u: PAGE)
            self.assertEqual(page.title, "Desks | Acme")

    def test_a_normal_page_never_opens_the_browser(self):
        def never(url):
            raise AssertionError("the browser must not be used")
        page = pagereader.read_page(self.URL, FakeWeb(Resp(200, text=PAGE)), browser_fetch=never)
        self.assertEqual(page.title, "Desks | Acme")

    def test_not_found_and_server_errors_do_not_use_the_browser(self):
        def never(url):
            raise AssertionError("the browser must not be used")
        for status in (404, 500):
            with self.assertRaises(PageReadError):
                pagereader.read_page(self.URL, FakeWeb(Resp(status)), browser_fetch=never)

    def test_when_the_browser_fails_the_original_message_stays_and_the_reason_is_added(self):
        def fails(url):
            raise PageReadError("Google Chrome or Microsoft Edge was not found on this computer.")
        with self.assertRaises(PageReadError) as ctx:
            pagereader.read_page(self.URL, FakeWeb(Resp(403)), browser_fetch=fails)
        message = str(ctx.exception)
        self.assertIn("HTTP 403", message)
        self.assertIn("TAAS-reader", message)
        self.assertIn("Chrome or Microsoft Edge was not found", message)
        self.assertNotIsInstance(ctx.exception, PageBlockedError)

    def test_browser_html_is_cut_to_the_size_limit(self):
        big = "<html><body><p>" + "word " * 600_000 + "</p></body></html>"
        page = pagereader.read_page(self.URL, FakeWeb(Resp(403)), browser_fetch=lambda u: big)
        self.assertLessEqual(len(page.text), pagereader.MAX_TEXT_CHARS)


if __name__ == "__main__":
    unittest.main()
