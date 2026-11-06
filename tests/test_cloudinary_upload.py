"""Tests for uploading a picture to Cloudinary (the Cloudinary library is replaced by a fake; nothing is uploaded)."""

import sys  # replace a library during one test
import tempfile  # a temporary folder
import types  # build a fake library
import unittest  # test tools
from pathlib import Path  # file paths
from unittest import mock  # replace a value during one test

from tests.test_ui_smoke import UiBase, find, labels  # the screen test setup (also loads the stand-in toolkit)
from taas import cloudinary_upload
from taas.errors import CloudinaryError, ConfigError, ValidationError  # our error types

URL = "https://res.cloudinary.com/demo/image/upload/v1/desk.jpg"
ENV = "CLOUDINARY_CLOUD_NAME=democloud\nCLOUDINARY_API_KEY=key123\nCLOUDINARY_API_SECRET=secret456\n"


# A stand-in for the cloudinary library that remembers what it was given
def fake_cloudinary(result=None, error=None):
    calls = {"config": None, "upload": []}
    module = types.ModuleType("cloudinary")
    module.config = lambda **kw: calls.__setitem__("config", kw)
    uploader = types.ModuleType("cloudinary.uploader")

    def upload(path, **kw):
        calls["upload"].append((path, kw))
        if error:
            raise error
        return {"secure_url": URL} if result is None else result

    uploader.upload = upload
    module.uploader = uploader
    return module, uploader, calls


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.env = self.dir / ".env"
        self.picture = self.dir / "desk.jpg"
        self.picture.write_bytes(b"fake picture")
        patcher = mock.patch("taas.config.app_folder", return_value=self.dir)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_upload(self, **kw):
        module, uploader, calls = fake_cloudinary(**kw)
        with mock.patch.dict(sys.modules, {"cloudinary": module, "cloudinary.uploader": uploader}):
            return cloudinary_upload.upload_image(self.picture), calls

    def test_returns_the_secure_url_and_uses_the_env_settings(self):
        self.env.write_text(ENV)
        url, calls = self.run_upload()
        self.assertEqual(url, URL)
        self.assertEqual(calls["config"], {"cloud_name": "democloud", "api_key": "key123",
                                           "api_secret": "secret456", "secure": True})
        self.assertEqual(calls["upload"], [(str(self.picture), {})])

    def test_missing_settings_are_named_and_nothing_is_uploaded(self):
        self.env.write_text("CLOUDINARY_CLOUD_NAME=democloud\n")
        with self.assertRaises(ConfigError) as ctx:
            self.run_upload()
        self.assertIn("CLOUDINARY_API_KEY", str(ctx.exception))
        self.assertIn("CLOUDINARY_API_SECRET", str(ctx.exception))
        self.assertNotIn("secret456", str(ctx.exception))

    def test_no_env_file(self):
        with self.assertRaises(ConfigError):
            self.run_upload()

    def test_missing_file(self):
        self.env.write_text(ENV)
        self.picture.unlink()
        with self.assertRaises(ValidationError):
            self.run_upload()

    def test_cloudinary_failure_becomes_a_plain_error(self):
        self.env.write_text(ENV)
        with self.assertRaises(CloudinaryError) as ctx:
            self.run_upload(error=RuntimeError("Invalid api_key"))
        self.assertIn("Invalid api_key", str(ctx.exception))

    def test_no_url_in_the_reply(self):
        self.env.write_text(ENV)
        with self.assertRaises(CloudinaryError):
            self.run_upload(result={})


class UploadButtonTests(UiBase):
    def setUp(self):
        super().setUp()
        self.do_setup()
        self.to_article()
        self.screen = self.app.screen

    def pick(self, path):
        self.app.choose_picture = lambda: path

    def test_upload_shows_the_address_read_only_and_fills_the_address_box(self):
        self.pick("C:/pics/desk.jpg")
        with mock.patch.object(self.wf, "upload_image", return_value=URL) as upload:
            self.click("Upload image to cloud")
        upload.assert_called_once_with("C:/pics/desk.jpg")
        self.assertEqual(self.screen.uploaded_url.get(), URL)
        self.assertEqual(self.screen.uploaded_url.kw["state"], "readonly")
        self.assertEqual(self.screen.image_url.get(), URL)

    def test_failed_upload_shows_the_message_and_changes_nothing(self):
        self.pick("C:/pics/desk.jpg")
        with mock.patch.object(self.wf, "upload_image", side_effect=ConfigError("Add CLOUDINARY_API_KEY")):
            self.click("Upload image to cloud")
        self.assertIn("Add CLOUDINARY_API_KEY", labels(self.app))
        self.assertEqual(self.screen.uploaded_url.get(), "")
        self.assertEqual(self.screen.image_url.get(), "")

    def test_closing_the_file_window_does_nothing(self):
        self.pick("")
        with mock.patch.object(self.wf, "upload_image") as upload:
            self.click("Upload image to cloud")
        upload.assert_not_called()

    def test_generate_button_is_still_coming_soon(self):
        button = find(self.app, "CTkButton", "Generate images automatically (coming soon)")
        self.assertEqual(button.kw["state"], "disabled")


if __name__ == "__main__":
    unittest.main()
