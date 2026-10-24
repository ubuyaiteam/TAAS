"""Tests for the Ubuy theme, the logo, the icon file and the theme menu."""

import re  # check color codes
import tempfile  # temporary folders
import unittest  # test tools
from pathlib import Path  # file paths

from PIL import Image  # read the icon file

import make_icon  # the icon script (project folder)
from tests.test_ui_smoke import UiBase, find, labels, pump, stub_ctk, ui  # the screen test setup (loads the stand-in toolkit)
from taas import config  # settings
from taas.errors import ValidationError  # our error types
from taas.ui import theme  # the colors
from taas.ui.logo import ICON_SIZES, draw_logo, write_ico  # the logo

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
ROOT = Path(__file__).resolve().parent.parent


# The sizes stored in an .ico file
def icon_sizes(path):
    with Image.open(path) as icon:
        return sorted(icon.ico.sizes())


class ColorTests(unittest.TestCase):
    def test_brand_colors_are_the_ubuy_ones(self):
        self.assertEqual((theme.AMBER, theme.INK), ("#FFB100", "#151515"))

    def test_every_pair_has_a_light_and_a_dark_color(self):
        for name in ("WINDOW", "CARD", "CARD_TOP", "LINE", "FIELD", "FIELD_LINE", "TEXT", "TEXT_SOFT", "GREEN", "RED",
                     "NOTICE", "BUTTON_TEXT", "BUTTON_TEXT_OFF", "CHOICE_OFF", "SCROLL", "SCROLL_HOVER"):
            pair = getattr(theme, name)
            self.assertEqual(len(pair), 2, name)
            self.assertTrue(all(HEX.match(c) for c in pair), name)

    def test_text_can_be_read_in_both_modes(self):
        # (text color, background color); 4.5 is the usual bar for normal text
        pairs = {
            "text on window": (theme.TEXT, theme.WINDOW), "text on cards": (theme.TEXT, theme.CARD),
            "text on card headers": (theme.TEXT, theme.CARD_TOP), "text in fields": (theme.TEXT, theme.FIELD),
            "hints in fields": (theme.TEXT_SOFT, theme.FIELD), "hints on cards": (theme.TEXT_SOFT, theme.CARD),
            "good news on cards": (theme.GREEN, theme.CARD), "good news on window": (theme.GREEN, theme.WINDOW),
            "problems on cards": (theme.RED, theme.CARD), "problems on window": (theme.RED, theme.WINDOW),
            "problems in fields": (theme.RED, theme.FIELD), "text on the update notice": (theme.TEXT, theme.NOTICE),
            "text on a choice bar": (theme.BUTTON_TEXT, theme.CHOICE_OFF),
        }
        for name, (text, background) in pairs.items():
            for mode in (0, 1):
                self.assertGreaterEqual(theme.contrast(text[mode], background[mode]), 4.5, f"{name} ({'light' if mode == 0 else 'dark'})")

    def test_button_text_can_be_read_on_amber(self):
        self.assertGreaterEqual(theme.contrast(theme.INK, theme.AMBER), 4.5)
        self.assertGreaterEqual(theme.contrast(theme.INK, theme.AMBER_HOVER), 4.5)

    def test_contrast_maths(self):
        self.assertAlmostEqual(theme.contrast("#000000", "#FFFFFF"), 21.0, places=1)
        self.assertAlmostEqual(theme.contrast("#777777", "#777777"), 1.0)


class ApplyTests(unittest.TestCase):
    def test_overrides_are_well_formed(self):
        for widget, settings in theme.overrides().items():
            for key, value in settings.items():
                if key.endswith("color") or "_color" in key:
                    self.assertEqual(len(value), 2, f"{widget}.{key}")
                    self.assertTrue(all(HEX.match(c) for c in value), f"{widget}.{key}")

    def test_buttons_are_amber_with_dark_text(self):
        button = theme.overrides()["CTkButton"]
        self.assertEqual(button["fg_color"], ["#FFB100", "#FFB100"])
        self.assertEqual(button["text_color"], ["#151515", "#151515"])

    def test_only_settings_the_toolkit_knows_are_changed(self):
        class Fake:
            class ThemeManager:
                theme = {"CTkButton": {"fg_color": "old", "hover_color": "old", "something_else": "keep"}, "CTkLabel": {}}
        theme.apply(Fake)
        button = Fake.ThemeManager.theme["CTkButton"]
        self.assertEqual(button["fg_color"], ["#FFB100", "#FFB100"])
        self.assertEqual(button["something_else"], "keep")
        self.assertNotIn("text_color", button)  # a key the toolkit did not have is not invented
        self.assertEqual(Fake.ThemeManager.theme["CTkLabel"], {})
        self.assertNotIn("CTkEntry", Fake.ThemeManager.theme)  # a widget the toolkit did not have is not invented

    def test_apply_does_nothing_when_there_is_no_theme_manager(self):
        theme.apply(object())  # must not raise


class LogoTests(unittest.TestCase):
    def test_logo_has_the_asked_size_and_a_transparent_corner(self):
        for size in (16, 64, 256):
            image = draw_logo(size)
            self.assertEqual(image.size, (size, size))
            self.assertEqual(image.mode, "RGBA")
            self.assertLess(image.getpixel((0, 0))[3], 10)  # outside the rounded badge (about transparent)
            self.assertEqual(image.getpixel((size // 2, size // 2))[3], 255)  # inside it

    def test_icon_file_holds_every_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.ico"
            write_ico(path)
            self.assertEqual(icon_sizes(path), sorted((s, s) for s in ICON_SIZES))

    def test_the_icon_file_in_the_project_is_there_and_complete(self):
        path = ROOT / "assets" / "taas.ico"
        self.assertTrue(path.exists(), "Run: python make_icon.py")
        self.assertEqual(path, make_icon.TARGET)
        self.assertEqual(icon_sizes(path), sorted((s, s) for s in ICON_SIZES))

    def test_build_scripts_use_the_icon(self):
        for name in ("build_exe.bat", ".github/workflows/release.yml", ".github/workflows/build-exe.yml"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn("make_icon.py", text, name)
            self.assertIn("taas.ico", text, name)


class ThemeSettingTests(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(text, encoding="utf-8")
            return config.load_settings(path)

    def test_default_is_system(self):
        self.assertEqual(self.load("").theme_mode, "system")

    def test_saved_modes_are_read(self):
        self.assertEqual(self.load("THEME_MODE=dark\n").theme_mode, "dark")
        self.assertEqual(self.load("THEME_MODE= Light \n").theme_mode, "light")

    def test_unknown_value_falls_back_to_system(self):
        self.assertEqual(self.load("THEME_MODE=purple\n").theme_mode, "system")


class ThemeScreenTests(UiBase):
    def test_screens_use_the_theme_colors(self):
        self.assertEqual((ui.RED, ui.GREEN, ui.NEUTRAL), (theme.RED, theme.GREEN, theme.TEXT))

    def test_top_bar_shows_the_logo_and_the_theme_menu(self):
        app = self.app
        self.assertIsNotNone(app.logo_image)
        self.assertEqual(app.logo_image.size, (34, 34))
        self.assertTrue(any(type(w).__name__ == "CTkLabel" and w.kw.get("image") is app.logo_image for w in app.descendants()))
        self.assertEqual(app.theme_menu.get(), "System")
        self.assertEqual(app.theme_menu.kw["values"], ["System", "Light", "Dark"])

    def test_update_notice_uses_the_notice_color(self):
        self.assertEqual(self.app.update_bar.kw["fg_color"], theme.NOTICE)

    def test_choosing_dark_changes_the_look_and_is_remembered(self):
        stub_ctk.appearance_modes.clear()
        self.app.theme_menu.choose("Dark")
        self.assertEqual(stub_ctk.appearance_modes[-1], "dark")
        self.assertEqual(self.wf.settings.theme_mode, "dark")
        self.assertEqual(config.load_settings().theme_mode, "dark")  # written to the settings file

    def test_next_start_uses_the_remembered_choice(self):
        self.wf.set_theme_mode("light")
        stub_ctk.appearance_modes.clear()
        app = ui.App(self.wf)
        self.assertEqual(stub_ctk.appearance_modes[0], "light")
        self.assertEqual(app.theme_menu.get(), "Light")

    def test_a_wrong_theme_is_refused(self):
        with self.assertRaises(ValidationError):
            self.wf.set_theme_mode("purple")
        self.assertEqual(self.wf.settings.theme_mode, "system")

    def test_window_icon_is_set_a_moment_after_start(self):
        pump(self.app)
        self.assertEqual(len(self.app.icons), 1)
        self.assertTrue(Path(self.app.icons[0]).exists())
        self.assertEqual(icon_sizes(self.app.icons[0]), [(16, 16), (32, 32), (48, 48), (64, 64)])

    def test_a_broken_icon_never_stops_the_app(self):
        self.app.iconbitmap = lambda path: (_ for _ in ()).throw(RuntimeError("no icon"))
        self.app.apply_window_icon()  # must not raise


if __name__ == "__main__":
    unittest.main()
