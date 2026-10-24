"""Test setup: tests must never read or write the user's real TAAS folder or a real client_secret.json."""

import atexit  # run clean-up when the tests end
import os  # environment variables
import shutil  # delete a folder
import tempfile  # temporary folders
from pathlib import Path  # file paths

_SANDBOX = Path(tempfile.mkdtemp(prefix="taas-tests-"))  # a private folder for this test run
atexit.register(shutil.rmtree, _SANDBOX, ignore_errors=True)
os.environ["TAAS_HOME"] = str(_SANDBOX / "home")  # settings and tokens go here, not to %APPDATA%

from taas import config  # noqa: E402  (imported after the environment is set)

_EMPTY_APP_FOLDER = _SANDBOX / "app-folder"  # an app folder with no client_secret.json in it
_EMPTY_APP_FOLDER.mkdir()
config.app_folder = lambda: _EMPTY_APP_FOLDER
