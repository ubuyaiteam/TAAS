"""Tests for the version number, the update check and the release script."""

import tempfile  # temporary folders
import unittest  # test tools
from pathlib import Path  # file paths

import requests  # error types

import release  # the release script (project folder)
from taas import __version__, config, updates  # the code being tested
from taas.errors import NetworkError, UpdateError  # our error types


# A fake answer from GitHub
class FakeResponse:
    def __init__(self, status=200, data=None, bad_json=False):
        self.status_code, self._data, self._bad = status, data, bad_json

    def json(self):
        if self._bad:
            raise ValueError("not json")
        return self._data


# A fake web client: returns one prepared answer and remembers the request
class FakeHttp:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers or {}})
        if self.error:
            raise self.error
        return self.response


RELEASE = {"tag_name": "v1.3.0", "html_url": "https://github.com/o/r/releases/tag/v1.3.0", "body": "Pictures in articles"}


class VersionTests(unittest.TestCase):
    def test_newer_and_older(self):
        self.assertTrue(updates.is_newer("1.1.0", "1.0.0"))
        self.assertTrue(updates.is_newer("v1.10.0", "1.9.9"))  # 10 is more than 9, not text order
        self.assertFalse(updates.is_newer("1.0.0", "1.1.0"))
        self.assertFalse(updates.is_newer("1.1.0", "1.1.0"))
        self.assertFalse(updates.is_newer("1.0", "1.0.0"))  # the same version

    def test_release_beats_its_own_test_versions(self):
        self.assertTrue(updates.is_newer("1.0.0", "1.0.0-rc1"))
        self.assertTrue(updates.is_newer("1.0.0-rc2", "1.0.0-rc1"))
        self.assertTrue(updates.is_newer("1.0.0-rc1", "1.0.0-beta3"))
        self.assertFalse(updates.is_newer("1.0.0-rc1", "1.0.0"))

    def test_bad_version_text(self):
        with self.assertRaises(ValueError):
            updates.parse_version("latest")

    def test_the_app_has_a_version_the_checker_understands(self):
        updates.parse_version(__version__)


class CheckTests(unittest.TestCase):
    def check(self, http, repo="o/r", token="", current="1.1.0"):
        return updates.check_for_update(current, repo, token=token, http=http)

    def test_newer_release_is_reported(self):
        http = FakeHttp(FakeResponse(200, RELEASE))
        info = self.check(http)
        self.assertTrue(info.newer)
        self.assertEqual((info.latest, info.url, info.notes), ("1.3.0", RELEASE["html_url"], "Pictures in articles"))
        self.assertIn("1.3.0", info.message())
        self.assertTrue(http.calls[0]["url"].endswith("/repos/o/r/releases/latest"))
        self.assertNotIn("Authorization", http.calls[0]["headers"])

    def test_same_version_is_up_to_date(self):
        info = self.check(FakeHttp(FakeResponse(200, RELEASE)), current="1.3.0")
        self.assertFalse(info.newer)
        self.assertIn("latest version", info.message())

    def test_running_a_newer_build_than_the_release_is_not_an_update(self):
        self.assertFalse(self.check(FakeHttp(FakeResponse(200, RELEASE)), current="1.4.0").newer)

    def test_token_is_sent_when_given(self):
        http = FakeHttp(FakeResponse(200, RELEASE))
        self.check(http, token="abc")
        self.assertEqual(http.calls[0]["headers"]["Authorization"], "Bearer abc")

    def test_no_repository_set(self):
        for repo in ("", "   ", "not a repo", "a/b/c"):
            with self.assertRaises(UpdateError) as ctx:
                self.check(FakeHttp(FakeResponse(200, RELEASE)), repo=repo)
            self.assertIn("not set up", str(ctx.exception))

    def test_404_explains_private_repositories(self):
        with self.assertRaises(UpdateError) as ctx:
            self.check(FakeHttp(FakeResponse(404, {})))
        self.assertIn("UPDATE_TOKEN", str(ctx.exception))

    def test_other_errors_have_plain_messages(self):
        for status in (401, 403, 429):
            with self.assertRaises(UpdateError):
                self.check(FakeHttp(FakeResponse(status, {})))
        with self.assertRaises(UpdateError) as ctx:
            self.check(FakeHttp(FakeResponse(500, {})))
        self.assertIn("500", str(ctx.exception))

    def test_unreadable_answers(self):
        for response in (FakeResponse(200, bad_json=True), FakeResponse(200, {"no_tag": 1}),
                         FakeResponse(200, {"tag_name": "nightly"}), FakeResponse(200, ["list"])):
            with self.assertRaises(UpdateError):
                self.check(FakeHttp(response))

    def test_no_internet(self):
        with self.assertRaises(NetworkError):
            self.check(FakeHttp(error=requests.ConnectionError()))
        with self.assertRaises(NetworkError):
            self.check(FakeHttp(error=requests.Timeout()))

    def test_repo_setting_is_read_and_overrides_the_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("UPDATE_REPO= team/taas \nUPDATE_TOKEN=tok\n", encoding="utf-8")
            settings = config.load_settings(path)
        self.assertEqual((settings.update_repo, settings.update_token), ("team/taas", "tok"))
        self.assertEqual(updates.pick_repo(settings.update_repo), "team/taas")
        self.assertEqual(updates.pick_repo(""), updates.DEFAULT_REPO)

    def test_saving_settings_does_not_erase_the_update_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("UPDATE_REPO=team/taas\n", encoding="utf-8")
            settings = config.load_settings(path)
            config.save_settings(settings, path)
            self.assertEqual(config.load_settings(path).update_repo, "team/taas")


class ReleaseScriptTests(unittest.TestCase):
    def test_version_check(self):
        for good in ("1.2.0", "10.0.1", "1.2.0-rc1"):
            self.assertEqual(release.check_version(good), good)
        for bad in ("1.2", "v1.2.0", "1.2.0.1", "abc", "", "1.2.0 "):
            with self.assertRaises(release.ReleaseError):
                release.check_version(bad)

    def test_write_version_changes_only_the_version_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "__init__.py"
            path.write_text('"""Doc."""\n\n__version__ = "1.1.0"\nOTHER = "1.1.0"\n', encoding="utf-8")
            self.assertEqual(release.write_version(path, "1.2.0-rc1"), "1.1.0")
            self.assertEqual(path.read_text(encoding="utf-8"), '"""Doc."""\n\n__version__ = "1.2.0-rc1"\nOTHER = "1.1.0"\n')

    def test_write_version_needs_a_version_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "__init__.py"
            path.write_text("x = 1\n", encoding="utf-8")
            with self.assertRaises(release.ReleaseError):
                release.write_version(path, "1.2.0")

    def test_the_real_version_file_can_be_changed_by_the_script(self):
        text = release.VERSION_FILE.read_text(encoding="utf-8")
        self.assertTrue(release.VERSION_LINE.search(text))

    def test_release_workflow_exists_and_checks_the_tag(self):
        workflow = (release.ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        for part in ('tags:', '"v*"', "contents: write", "--prerelease", "gh release create", "TAAS.exe"):
            self.assertIn(part, workflow)


if __name__ == "__main__":
    unittest.main()
