"""Find out whether a newer version of TAAS was released on GitHub."""

import re  # read version numbers
from dataclasses import dataclass  # simple data classes

import requests  # send web requests

from .errors import NetworkError, UpdateError  # our error types

# The GitHub repository that holds the releases, written owner/name (for example "acme/taas").
# Set it once here. A team member can also override it with UPDATE_REPO in the .env file.
DEFAULT_REPO = "ubuyaiteam/TAAS"

API_ROOT = "https://api.github.com/repos"  # start of every GitHub address we use
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")  # owner/name
PRE_ORDER = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "rc": 2}  # earlier test versions rank lower
NOTES_LIMIT = 600  # how many characters of the release notes we keep


# What the check found
@dataclass
class UpdateInfo:
    current: str  # the version that is running
    latest: str  # the newest released version
    url: str  # page where the new version can be downloaded
    notes: str  # what changed (cut short)
    newer: bool  # True when latest is newer than current
    download_url: str = ""  # verified TAAS.exe asset from the release
    digest: str = ""  # GitHub's published asset digest

    # One plain sentence for the user
    def message(self):
        if self.newer:
            return f"A new version is available: {self.latest} (you have {self.current})."
        return f"You have the latest version ({self.current})."


# "v1.2.3" or "1.2.0-rc1" -> something that can be compared; a release beats its own test versions
def parse_version(text):
    match = re.match(r"^\s*[vV]?(\d+(?:\.\d+){0,3})(?:[-.]?([A-Za-z]+)\.?(\d*))?\s*$", text or "")
    if not match:
        raise ValueError(f"Not a version number: {text!r}")
    numbers = [int(part) for part in match.group(1).split(".")]
    numbers += [0] * (4 - len(numbers))  # 1.2 equals 1.2.0
    if match.group(2):
        label = PRE_ORDER.get(match.group(2).lower(), -1)
        return tuple(numbers), (0, label, int(match.group(3) or 0))
    return tuple(numbers), (1, 0, 0)


# Is `latest` newer than `current`?
def is_newer(latest, current):
    return parse_version(latest) > parse_version(current)


# Which repository to ask: the .env value, or the built-in one
def pick_repo(configured):
    return (configured or "").strip() or DEFAULT_REPO


# Ask GitHub for the newest published release (test versions and drafts are skipped by GitHub)
def check_for_update(current, repo, token="", http=requests, timeout=10):
    repo = (repo or "").strip()
    if not REPO_PATTERN.match(repo):
        raise UpdateError(
            "Update checking is not set up yet. The GitHub repository name (owner/name) is missing. "
            "Ask the person who maintains TAAS to set it."
        )
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "TAAS-update-check"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = http.get(f"{API_ROOT}/{repo}/releases/latest", headers=headers, timeout=timeout)
    except (requests.ConnectionError, requests.Timeout):
        raise NetworkError("Could not reach GitHub to look for updates. Check the internet connection.")
    except requests.RequestException:
        raise UpdateError("The update check failed.")

    if resp.status_code == 404:
        raise UpdateError(
            f"GitHub found no published release for {repo}. Either no release was published yet, "
            "or the repository is private (a private repository needs UPDATE_TOKEN in the TAAS settings file)."
        )
    if resp.status_code in (401, 403, 429):
        raise UpdateError("GitHub did not allow the update check right now (too many requests, or the token is wrong). Try again later.")
    if resp.status_code >= 400:
        raise UpdateError(f"GitHub gave an error while looking for updates (HTTP {resp.status_code}).")
    try:
        data = resp.json()
        tag = str(data["tag_name"])
        assets = data.get("assets", [])
        if not isinstance(assets, list):
            assets = []
        installer = next(
            (
                asset for asset in assets
                if isinstance(asset, dict) and str(asset.get("name", "")).casefold() == "taas.exe"
            ),
            {},
        )
        return UpdateInfo(
            current=current,
            latest=tag.lstrip("vV"),
            url=str(data.get("html_url") or f"https://github.com/{repo}/releases"),
            notes=str(data.get("body") or "").strip()[:NOTES_LIMIT],
            newer=is_newer(tag, current),
            download_url=str(installer.get("browser_download_url") or ""),
            digest=str(installer.get("digest") or ""),
        )
    except (ValueError, KeyError, TypeError):
        raise UpdateError("GitHub gave an answer that could not be understood.")
