"""Checks for the look of the screens: sidebar, steps, colors and the Dark mode switch.

The stand-in toolkit draws nothing, so this checks the values the code gives to the widgets,
not how the window looks.
"""

import re  # match color codes
import unittest  # test tools
from unittest import mock  # swap things for the length of one test

from tests.test_ui_smoke import UiBase, find, labels, ui  # the UI test setup (it also swaps in the stand-in toolkit)

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
COLOR_KEYS = ("fg_color", "text_color", "border_color", "hover_color", "button_color", "selected_color",
              "unselected_color", "checkmark_color")
THEME_NAMES = ("PAGE_BG", "SIDEBAR_BG", "CARD_BG", "FIELD_BG", "LINE", "INPUT_LINE", "INK", "MUTED", "ACCENT",
               "ACCENT_HOVER", "ACCENT_TEXT", "ACCENT_SOFT", "SELECTED", "AMBER", "RED", "GREEN", "WARN", "NEUTRAL")


def step_state(app, number):
    """What the sidebar shows for a step: 'done', 'here' or 'later'."""
    row, circle, label = app.step_rows[number - 1]
    if circle.kw.get("text") == "✓":
        return "done"
    return "here" if row.kw.get("fg_color") == ui.ACCENT_SOFT else "later"


class ThemeTests(UiBase):
    def test_light_mode_uses_signature_ubuy_yellow_palette(self):
        self.assertEqual(ui.PAGE_BG[0], "#FFFDF7")
        self.assertEqual(ui.FIELD_BG[0], "#F5F1E5")
        self.assertEqual(ui.ACCENT[0], "#FFB900")
        self.assertEqual(ui.INK[0], "#20243A")
        self.assertEqual(ui.main_button()["text_color"][0], "#20243A")
        self.assertEqual(ui.ACCENT_TEXT[0], "#805800")

    def test_theme_colors_are_hex_codes(self):
        for name in THEME_NAMES:
            value = getattr(ui, name)
            for one in (value if isinstance(value, tuple) else (value,)):  # a (light, dark) pair or one color
                self.assertRegex(one, HEX, name)

    def test_no_widget_gets_an_empty_color(self):
        # the real toolkit raises an error for a color that is None
        for show in (ui.SetupScreen, ui.InputScreen):
            self.app.show(show)
            for widget in self.app.descendants():
                for key in COLOR_KEYS:
                    if key in widget.kw:
                        self.assertIsNotNone(widget.kw[key], f"{show.__name__}: {key} is None")

    def test_app_starts_in_light_mode(self):
        modes = []
        fake_app = lambda auto_check=False: type("FakeApp", (), {"mainloop": lambda self: None})()
        with mock.patch.object(ui.ctk, "set_appearance_mode", modes.append), mock.patch.object(ui, "App", fake_app):
            ui.run()
        self.assertEqual(modes, ["light"])

    def test_dark_mode_button_switches_and_switches_back(self):
        modes = []
        with mock.patch.object(ui.ctk, "set_appearance_mode", modes.append):
            self.click("Dark mode")
            self.assertEqual(modes, ["dark"])
            find(self.app, "CTkButton", "Light mode").invoke()
        self.assertEqual(modes, ["dark", "light"])
        find(self.app, "CTkButton", "Dark mode")

    def test_sidebar_has_the_four_steps_and_the_small_buttons(self):
        text = labels(self.app)
        for name in ("Add pages", "Check details", "Review article", "Publish"):
            self.assertIn(name, text)
        for name in ("Check for updates", "Settings"):
            find(self.app, "CTkButton", name)

    def test_sidebar_follows_the_steps(self):
        self.assertEqual([step_state(self.app, n) for n in (1, 2, 3, 4)], ["later"] * 4)  # Setup: none yet
        self.do_setup()
        self.assertEqual([step_state(self.app, n) for n in (1, 2, 3, 4)], ["here", "later", "later", "later"])
        self.to_article()
        self.assertEqual([step_state(self.app, n) for n in (1, 2, 3, 4)], ["done", "done", "here", "later"])

    def test_settings_button_opens_setup(self):
        self.do_setup()
        self.click("Settings")
        self.assertEqual(self.screen_name(), "SetupScreen")

    def test_looks_good_hint_for_web_addresses(self):
        self.assertTrue(ui.looks_like_address("https://www.u-buy.com.au/deals/halloween-sale"))
        self.assertTrue(ui.looks_like_address("  http://example.com/a  "))
        for bad in ("", "https://", "u-buy.com.au", "https://nodot", "https://a b.com"):
            self.assertFalse(ui.looks_like_address(bad), bad)
        self.do_setup()
        screen = self.app.screen
        screen.urls[0].insert(0, "https://www.u-buy.com.au/deals/halloween-sale")
        find(self.app, "CTkButton", "+ Add another URL").invoke()
        screen.refresh_ticks()
        self.assertIn("Looks good", screen.ticks[0].kw["text"])
        self.assertEqual(screen.ticks[1].kw["text"], "")


if __name__ == "__main__":
    unittest.main()
