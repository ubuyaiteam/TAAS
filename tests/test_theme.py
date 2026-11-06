"""Tests for the app icon and theme settings."""

import struct  # read Windows icon headers
import tempfile  # temporary folders
import unittest  # test tools
from unittest import mock  # replace platform paths in tests
from pathlib import Path  # file paths

from tests.test_ui_smoke import UiBase, ui  # the screen test setup (loads the stand-in toolkit)
from taas import config  # settings
from taas.errors import ValidationError  # our error types

ROOT = Path(__file__).resolve().parent.parent
LOGO_ICON = ROOT / "assets" / "taas-logo.ico"
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


# Read the image sizes from each PNG frame in a Windows icon file.
def icon_sizes(path):
    data = Path(path).read_bytes()
    reserved, image_type, count = struct.unpack_from("<HHH", data)
    if reserved != 0 or image_type != 1:
        raise ValueError(f"{path} is not a Windows icon file.")
    sizes = []
    for index in range(count):
        width, height, _, _, _, _, frame_size, frame_offset = struct.unpack_from(
            "<BBBBHHII", data, 6 + 16 * index
        )
        width, height = width or 256, height or 256
        frame = data[frame_offset:frame_offset + frame_size]
        if frame[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"{path} contains a non-PNG icon frame.")
        frame_width, frame_height = struct.unpack_from(">II", frame, 16)
        if (frame_width, frame_height) != (width, height):
            raise ValueError(f"{path} contains a frame with inconsistent dimensions.")
        sizes.append((width, height))
    return sorted(sizes)


class IconTests(unittest.TestCase):
    def test_project_icon_is_a_complete_multisize_windows_icon(self):
        self.assertTrue(LOGO_ICON.exists())
        self.assertEqual(icon_sizes(LOGO_ICON), sorted((s, s) for s in ICON_SIZES))

    def test_build_scripts_use_the_icon(self):
        release_workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
        self.assertIn("TAAS.spec", release_workflow)
        build_workflow = (ROOT / ".github/workflows/build-exe.yml").read_text(encoding="utf-8")
        spec = (ROOT / "TAAS.spec").read_text(encoding="utf-8")
        self.assertIn("('assets/taas-logo.ico', 'assets')", spec)
        self.assertIn("exclude_binaries=True", spec)
        self.assertIn("coll = COLLECT(", spec)
        self.assertIn("upx=False", spec)
        build_script = (ROOT / "build_exe.bat").read_text(encoding="utf-8")
        self.assertIn("TAAS.spec", build_script)
        self.assertIn("taas_setup.iss", build_script)
        self.assertNotIn("test_main5.py", build_script)
        self.assertIn("/DMyAppVersion=%APP_VERSION%", build_script)
        installer = (ROOT / "taas_setup.iss").read_text(encoding="utf-8")
        self.assertIn("MyAppVersion", installer)
        self.assertIn('SetupIconFile=assets\\taas-logo.ico', installer)
        self.assertIn('Source: "dist\\TAAS\\*"', installer)
        self.assertIn('Source: "client_secret.json"', installer)
        self.assertIn("TAAS.spec", build_workflow)
        self.assertNotIn("--onefile", build_workflow)


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


class ThemeSettingsTests(UiBase):
    def test_window_uses_the_taas_icon(self):
        with mock.patch.object(ui.sys, "platform", "win32"):
            self.app.set_window_icon()
        self.assertEqual(Path(self.app.icons[-1]), LOGO_ICON)

    def test_frozen_app_loads_the_bundled_icon(self):
        with tempfile.TemporaryDirectory() as tmp:
            icon = Path(tmp) / "assets" / "taas-logo.ico"
            icon.parent.mkdir()
            icon.write_bytes(b"icon")
            with mock.patch.object(ui.sys, "platform", "win32"), \
                    mock.patch.object(ui.sys, "_MEIPASS", tmp, create=True):
                self.app.set_window_icon()
            self.assertEqual(Path(self.app.icons[-1]), icon)

    def test_a_wrong_theme_is_refused(self):
        with self.assertRaises(ValidationError):
            self.wf.set_theme_mode("purple")
        self.assertEqual(self.wf.settings.theme_mode, "system")


if __name__ == "__main__":
    unittest.main()
