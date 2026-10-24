"""Tests for the version number, the update check and the release script."""

import hashlib  # checks the downloaded executable
import subprocess  # checks the detached updater process
import tempfile  # temporary folders
import unittest  # test tools
from unittest import mock  # replace the web client and process launcher
from pathlib import Path  # file paths

import requests  # error types

import release  # the release script (project folder)
from taas import __version__, config, self_update, updates  # the code being tested
from taas.errors import NetworkError, UpdateError  # our error types
from taas.updates import UpdateInfo  # update details


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


class FakeDownloadResponse:
    def __init__(self, content=b"new TAAS executable", status=200):
        self.content, self.status_code = content, status
        self.closed = False

    def iter_content(self, chunk_size):
        yield self.content[:5]
        yield self.content[5:]

    def close(self):
        self.closed = True


class FakeDownloadHttp:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def get(self, url, headers=None, stream=False, timeout=None):
        self.calls.append((url, headers, stream, timeout))
        if self.error:
            raise self.error
        return self.response


RELEASE = {
    "tag_name": "v1.3.0",
    "html_url": "https://github.com/o/r/releases/tag/v1.3.0",
    "body": "Pictures in articles",
    "assets": [{
        "name": "TAAS.exe",
        "browser_download_url": "https://github.com/o/r/releases/download/v1.3.0/TAAS.exe",
        "digest": "sha256:" + "a" * 64,
    }],
}


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
        self.assertEqual(info.download_url, RELEASE["assets"][0]["browser_download_url"])
        self.assertEqual(info.digest, RELEASE["assets"][0]["digest"])
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

    def test_release_without_installer_has_no_download_metadata(self):
        info = self.check(FakeHttp(FakeResponse(200, {
            "tag_name": "v1.3.0",
            "assets": [{"name": "USER_GUIDE.md", "browser_download_url": "https://github.com/o/r/guide"}],
        })))
        self.assertEqual((info.download_url, info.digest), ("", ""))

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


class InstallUpdateTests(unittest.TestCase):
    CONTENT = b"new TAAS executable"

    def make_info(self, digest=None, download_url=None, newer=True):
        return UpdateInfo(
            "1.1.0", "1.2.0", "https://github.com/o/r/releases/tag/v1.2.0", "", newer,
            download_url if download_url is not None else
            "https://github.com/o/r/releases/download/v1.2.0/TAAS.exe",
            digest if digest is not None else "sha256:" + hashlib.sha256(self.CONTENT).hexdigest(),
        )

    def run_install(self, directory, info=None, content=None, popen=None, token=""):
        directory = Path(directory)
        target = directory / "TAAS.exe"
        target.write_bytes(b"old TAAS executable")
        update_dir = directory / "download"
        update_dir.mkdir()
        response = FakeDownloadResponse(content or self.CONTENT)
        http = FakeDownloadHttp(response)
        launcher = popen or mock.Mock()
        with mock.patch.object(self_update.tempfile, "mkdtemp", return_value=str(update_dir)):
            self_update.install_update(
                info or self.make_info(), token=token, executable_path=target, http=http, popen=launcher,
                platform="win32", frozen=True,
                powershell=r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                process_id=321,
            )
        return target, update_dir, response, http, launcher

    def test_download_is_verified_and_a_detached_installer_is_started(self):
        with tempfile.TemporaryDirectory() as tmp:
            target, update_dir, response, http, launcher = self.run_install(tmp)
            args, kwargs = launcher.call_args
            command = args[0]
            self.assertEqual(http.calls[0][0], self.make_info().download_url)
            self.assertTrue(http.calls[0][2])
            self.assertTrue(response.closed)
            self.assertNotIn("Authorization", http.calls[0][1])
            self.assertEqual((update_dir / "TAAS.exe").read_bytes(), self.CONTENT)
            self.assertEqual(Path(command[command.index("-TargetPath") + 1]), target.resolve())
            self.assertEqual(command[command.index("-WaitPid") + 1], "321")
            self.assertIn("Wait-Process", Path(command[command.index("-File") + 1]).read_text(encoding="utf-8"))
            expected_flags = (
                getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0)
            )
            self.assertEqual(kwargs["creationflags"], expected_flags)

    def test_private_release_token_is_sent_for_the_asset_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, http, _ = self.run_install(tmp, token="private-token")
            self.assertEqual(http.calls[0][1]["Authorization"], "Bearer private-token")

    def test_bad_checksum_never_starts_the_installer(self):
        with tempfile.TemporaryDirectory() as tmp:
            update_dir = Path(tmp) / "download"
            update_dir.mkdir()
            target = Path(tmp) / "TAAS.exe"
            target.write_bytes(b"old")
            response = FakeDownloadResponse(self.CONTENT)
            launcher = mock.Mock()
            with mock.patch.object(self_update.tempfile, "mkdtemp", return_value=str(update_dir)):
                with self.assertRaisesRegex(UpdateError, "checksum"):
                    self_update.install_update(
                        self.make_info(digest="sha256:" + "0" * 64),
                        executable_path=target,
                        http=FakeDownloadHttp(response), popen=launcher,
                        platform="win32", frozen=True, powershell="powershell.exe",
                    )
            launcher.assert_not_called()
            self.assertFalse(update_dir.exists())
            self.assertTrue(response.closed)

    def test_unsafe_or_missing_download_metadata_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "TAAS.exe"
            target.write_bytes(b"old")
            for info in (
                self.make_info(download_url="http://github.com/o/r/TAAS.exe"),
                self.make_info(digest=""),
                self.make_info(newer=False),
            ):
                with self.assertRaises(UpdateError):
                    self_update.install_update(
                        info, executable_path=target, http=FakeDownloadHttp(),
                        platform="win32", frozen=True, powershell="powershell.exe",
                    )

    def test_source_run_does_not_replace_the_python_executable(self):
        with self.assertRaisesRegex(UpdateError, "installed Windows TAAS.exe"):
            self_update.install_update(
                self.make_info(), platform="win32", frozen=False, powershell="powershell.exe"
            )

    def test_connection_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "TAAS.exe"
            target.write_bytes(b"old")
            with mock.patch.object(self_update.tempfile, "mkdtemp", return_value=str(Path(tmp) / "download")):
                with self.assertRaises(NetworkError):
                    self_update.install_update(
                        self.make_info(), executable_path=target,
                        http=FakeDownloadHttp(error=requests.ConnectionError("offline")),
                        platform="win32", frozen=True, powershell="powershell.exe",
                    )


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
