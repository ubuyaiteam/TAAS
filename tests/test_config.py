import tempfile  # temporary files and folders for tests
import unittest  # test tools
from pathlib import Path  # file paths

from taas import config  # the code being used or tested
from taas.errors import ConfigError  # our error types


# Tests for settings
class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / ".env"

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_gives_defaults(self):
        s = config.load_settings(self.path)
        self.assertEqual((s.min_words, s.max_words), (300, 400))
        self.assertEqual(s.gemini_api_key, "")
        self.assertIsNone(s.post_limit_per_day)

    def test_save_and_load_round_trip(self):
        s = config.Settings(
            gemini_api_key="abc123", blog_id="999", min_words=250,
            max_words=450, post_limit_per_day=2,
        )
        config.save_settings(s, self.path)
        loaded = config.load_settings(self.path)
        self.assertEqual(loaded, s)

    def test_save_setting_keeps_other_lines(self):
        self.path.write_text("OTHER=keepme\n", encoding="utf-8")
        config.save_setting(config.KEY_GEMINI, "k1", self.path)
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("OTHER=keepme", text)
        self.assertIn("GEMINI_API_KEY=k1", text)

    def test_no_password_setting_exists(self):
        names = {f for f in config.Settings.__dataclass_fields__}
        self.assertFalse(any("password" in n for n in names))

    def test_non_numeric_word_count_is_rejected(self):
        self.path.write_text("MIN_WORDS=abc\n", encoding="utf-8")
        with self.assertRaises(ConfigError):
            config.load_settings(self.path)

    def test_min_larger_than_max_is_rejected(self):
        self.path.write_text("MIN_WORDS=500\nMAX_WORDS=400\n", encoding="utf-8")
        with self.assertRaises(ConfigError):
            config.load_settings(self.path)

    def test_post_limit_must_be_positive(self):
        self.path.write_text("POST_LIMIT_PER_DAY=0\n", encoding="utf-8")
        with self.assertRaises(ConfigError):
            config.load_settings(self.path)

    def test_client_secret_path_default_and_custom(self):
        custom = config.Settings(client_secret_file="C:/x/client.json")
        self.assertEqual(custom.client_secret_path(), Path("C:/x/client.json"))
        self.assertEqual(config.Settings().client_secret_path().name, "client_secret.json")

    def test_client_secret_is_found_next_to_the_app(self):
        import os  # environment variables
        from unittest import mock  # replace a function during a test
        home, beside = Path(self.tmp.name) / "home", Path(self.tmp.name) / "beside"
        beside.mkdir()
        with mock.patch.dict(os.environ, {"TAAS_HOME": str(home)}), mock.patch.object(config, "app_folder", lambda: beside):
            self.assertEqual(config.Settings().client_secret_path(), home / "client_secret.json")  # nothing exists yet
            (beside / "client_secret.json").write_text("{}")
            self.assertEqual(config.Settings().client_secret_path(), beside / "client_secret.json")
            (home / "client_secret.json").write_text("{}")  # the settings folder wins
            self.assertEqual(config.Settings().client_secret_path(), home / "client_secret.json")


if __name__ == "__main__":
    unittest.main()
