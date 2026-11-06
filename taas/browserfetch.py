"""Fallback page reader: opens the page in the Chrome or Edge already installed on this computer (Playwright).

Used only when a website refuses the normal reader (HTTP 401, 403 or 429). The browser runs hidden, unless the
.env file next to the app has BROWSER_VISIBLE=1 (some websites let a visible window through but block a hidden one).
"""

from dotenv import dotenv_values  # read the .env file

from . import config  # where the .env file is
from .errors import PageReadError  # our error types

BROWSER_CHANNELS = ("chrome", "msedge")  # installed browsers to try, in this order
LOAD_TIMEOUT_MS = 30_000  # how long to wait for the page to open
SETTLE_TIMEOUT_MS = 5_000  # extra wait for the page to finish loading its content
BLOCKED_STATUSES = (401, 403, 429)
KEY_VISIBLE = "BROWSER_VISIBLE"  # name used inside the .env file (1, true, yes or on = show the window)


# True when the .env file next to the app asks for a visible browser window
def browser_is_visible():
    path = config.app_folder() / ".env"
    values = dotenv_values(path) if path.exists() else {}
    return (values.get(KEY_VISIBLE) or "").strip().lower() in ("1", "true", "yes", "on")


# Open the page in a hidden browser and return its HTML
def fetch_html(url):
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise PageReadError("the browser tool (Playwright) is not installed.")

    visible = browser_is_visible()
    try:
        with sync_playwright() as playwright:
            browser = None
            for channel in BROWSER_CHANNELS:
                try:
                    browser = playwright.chromium.launch(channel=channel, headless=not visible)
                    break
                except PlaywrightError:
                    continue
            if browser is None:
                raise PageReadError("Google Chrome or Microsoft Edge was not found on this computer.")
            try:
                page = browser.new_page()
                response = page.goto(url, wait_until="domcontentloaded", timeout=LOAD_TIMEOUT_MS)
                status = response.status if response else 0
                if status in BLOCKED_STATUSES:
                    raise PageReadError(f"the website blocked the browser too (HTTP {status}).")
                if status >= 400:
                    raise PageReadError(f"the website gave an error in the browser (HTTP {status}).")
                try:
                    page.wait_for_load_state("networkidle", timeout=SETTLE_TIMEOUT_MS)
                except PlaywrightTimeout:
                    pass  # some pages never go quiet; read what has loaded
                return page.content()
            finally:
                browser.close()
    except PageReadError:
        raise
    except PlaywrightTimeout:
        raise PageReadError("the page took too long to open in the browser.")
    except PlaywrightError as error:
        raise PageReadError(f"the browser could not open the page ({str(error).splitlines()[0] if str(error) else 'unknown error'}).")
