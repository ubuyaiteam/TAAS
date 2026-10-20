"""Settings kept in a .env file. No passwords are stored here."""

from __future__ import annotations  # allow newer type hints

import os  # system and file-permission tools
import sys  # tells us if we run as a packaged .exe
from dataclasses import dataclass  # simple data classes
from pathlib import Path  # file paths
from typing import Optional  # type hints

from dotenv import dotenv_values, set_key  # read and write the .env file

from .errors import ConfigError  # our error types

DEFAULT_MIN_WORDS = 300  # default shortest article (words)
DEFAULT_MAX_WORDS = 400  # default longest article (words)
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"  # model name given by the reviewer (not verified yet)

KEY_GEMINI = "GEMINI_API_KEY"  # name used inside the .env file
KEY_BLOG_ID = "BLOGGER_BLOG_ID"
KEY_GEMINI_MODEL = "GEMINI_MODEL"
KEY_MIN_WORDS = "MIN_WORDS"
KEY_MAX_WORDS = "MAX_WORDS"
KEY_POST_LIMIT = "POST_LIMIT_PER_DAY"
KEY_CLIENT_SECRET = "GOOGLE_CLIENT_SECRET_FILE"


def app_dir() -> Path:
    """Folder where TAAS keeps its files."""
    # TAAS_HOME lets you use another folder
    override = os.environ.get("TAAS_HOME")
    if override:
        folder = Path(override)
    # Windows: use the AppData folder
    elif os.name == "nt":
        folder = Path(os.environ.get("APPDATA", str(Path.home()))) / "TAAS"
    else:
        folder = Path.home() / ".taas"
    # create the folder if it is missing
    folder.mkdir(parents=True, exist_ok=True)
    return folder


# Folder next to the app: next to the .exe, or the project folder when run from source
def app_folder() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


# Path of the .env file
def env_path() -> Path:
    return app_dir() / ".env"


# Path of the sign-in file
def token_path() -> Path:
    return app_dir() / "token.json"


# All user settings
@dataclass
class Settings:
    gemini_api_key: str = ""  # user's own Gemini key
    gemini_model: str = DEFAULT_GEMINI_MODEL  # Gemini model to use
    blog_id: str = ""  # chosen Blogger blog
    min_words: int = DEFAULT_MIN_WORDS  # shortest article
    max_words: int = DEFAULT_MAX_WORDS  # longest article
    post_limit_per_day: Optional[int] = None  # optional daily limit
    client_secret_file: str = ""  # path to the Google client file

    def client_secret_path(self) -> Path:
        if self.client_secret_file:  # 1. a path set in the .env file
            return Path(self.client_secret_file)
        saved = app_dir() / "client_secret.json"  # 2. the TAAS settings folder
        if saved.exists():
            return saved
        beside = app_folder() / "client_secret.json"  # 3. next to the app (ships with the .exe)
        return beside if beside.exists() else saved  # if none exists, help messages show #2


# Read a whole number from the settings
def _int(values: dict, key: str, default: Optional[int]) -> Optional[int]:
    # empty value = use the default
    raw = (values.get(key) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"Setting {key} must be a whole number, not '{raw}'.")


def load_settings(path: Optional[Path] = None) -> Settings:
    """Read settings. No file means default values."""
    path = Path(path) if path else env_path()
    # read the file without changing system settings
    values = dotenv_values(path) if path.exists() else {}

    settings = Settings(
        gemini_api_key=(values.get(KEY_GEMINI) or "").strip(),
        gemini_model=(values.get(KEY_GEMINI_MODEL) or "").strip() or DEFAULT_GEMINI_MODEL,
        blog_id=(values.get(KEY_BLOG_ID) or "").strip(),
        min_words=_int(values, KEY_MIN_WORDS, DEFAULT_MIN_WORDS),
        max_words=_int(values, KEY_MAX_WORDS, DEFAULT_MAX_WORDS),
        post_limit_per_day=_int(values, KEY_POST_LIMIT, None),
        client_secret_file=(values.get(KEY_CLIENT_SECRET) or "").strip(),
    )
    validate_settings(settings)
    return settings


# Check the settings make sense
def validate_settings(settings: Settings) -> None:
    if settings.min_words < 1:
        raise ConfigError("Minimum word count must be at least 1.")
    if settings.min_words > settings.max_words:
        raise ConfigError(
            "Minimum word count cannot be larger than the maximum word count."
        )
    if settings.post_limit_per_day is not None and settings.post_limit_per_day < 1:
        raise ConfigError("The posting limit must be at least 1 per day.")


def save_setting(key: str, value: str, path: Optional[Path] = None) -> None:
    """Save one setting. Other lines stay."""
    path = Path(path) if path else env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("", encoding="utf-8")
    # quote_mode never = no quotes around values
    set_key(str(path), key, str(value), quote_mode="never")


# Save all settings
def save_settings(settings: Settings, path: Optional[Path] = None) -> None:
    validate_settings(settings)
    save_setting(KEY_GEMINI, settings.gemini_api_key, path)
    save_setting(KEY_GEMINI_MODEL, settings.gemini_model, path)
    save_setting(KEY_BLOG_ID, settings.blog_id, path)
    save_setting(KEY_MIN_WORDS, str(settings.min_words), path)
    save_setting(KEY_MAX_WORDS, str(settings.max_words), path)
    save_setting(
        KEY_POST_LIMIT,
        "" if settings.post_limit_per_day is None else str(settings.post_limit_per_day),
        path,
    )
    save_setting(KEY_CLIENT_SECRET, settings.client_secret_file, path)
