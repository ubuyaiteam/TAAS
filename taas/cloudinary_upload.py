"""Uploads one picture to Cloudinary and gives back its web address.

The Cloudinary details are read from the .env file (never typed in the app):
  CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
"""

from pathlib import Path  # file paths

from dotenv import dotenv_values  # read the .env file

from . import config  # where the .env file is
from .errors import CloudinaryError, ConfigError, ValidationError  # our error types

KEY_CLOUD_NAME = "CLOUDINARY_CLOUD_NAME"  # names used inside the .env file
KEY_API_KEY = "CLOUDINARY_API_KEY"  # names used inside the .env file
KEY_API_SECRET = "CLOUDINARY_API_SECRET"  # names used inside the .env file


# Read the three Cloudinary settings from the .env file; stop with a clear message if one is missing
def load_cloudinary_settings():
    path = config.app_folder() / ".env"
    values = dotenv_values(path) if path.exists() else {}
    settings = {key: (values.get(key) or "").strip() for key in (KEY_CLOUD_NAME, KEY_API_KEY, KEY_API_SECRET)}
    missing = [key for key, value in settings.items() if not value]
    if missing:
        raise ConfigError(f"Add {', '.join(missing)} to the .env file ({path}), then try again.")
    return settings


# Upload the picture at `path`; returns its secure_url
def upload_image(path):
    file = Path(str(path or "").strip())
    if not file.is_file():
        raise ValidationError("Choose a picture file to upload.")
    settings = load_cloudinary_settings()

    import cloudinary  # imported here so the rest of the app loads even if it is not installed
    import cloudinary.uploader

    cloudinary.config(
        cloud_name=settings[KEY_CLOUD_NAME],
        api_key=settings[KEY_API_KEY],
        api_secret=settings[KEY_API_SECRET],
        secure=True,
    )
    try:
        result = cloudinary.uploader.upload(str(file))
    except Exception as error:  # Cloudinary raises its own error types; show its text
        raise CloudinaryError(f"Cloudinary could not upload the picture: {error}")
    url = (result or {}).get("secure_url", "")
    if not url:
        raise CloudinaryError("Cloudinary did not return a web address for the picture.")
    return url
