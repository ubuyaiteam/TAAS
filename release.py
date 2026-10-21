"""Make a new TAAS release.

    python release.py 1.2.0          bump the version, test, commit and tag (nothing is uploaded)
    python release.py 1.2.0 --push   the same, then upload the commit and the tag to GitHub

Pushing the tag starts the "Release TAAS.exe" workflow on GitHub. It builds the .exe and publishes it
as a GitHub Release. The running apps then tell their users that a new version is available.
A version with a dash, like 1.2.0-rc1, is published as a test release that users are NOT told about.
"""

import argparse  # read the command line
import re  # find patterns in text
import subprocess  # run git and the tests
import sys  # python path and exit codes
from pathlib import Path  # file paths

ROOT = Path(__file__).resolve().parent  # the project folder
VERSION_FILE = ROOT / "taas" / "__init__.py"  # the one place the version is written
VERSION_OK = re.compile(r"^\d+\.\d+\.\d+(-[A-Za-z]+\d*)?$")  # 1.2.0 or 1.2.0-rc1
VERSION_LINE = re.compile(r'^__version__ = "[^"]*"', re.MULTILINE)


class ReleaseError(Exception):
    """Something stops the release. Its text says what to do."""


# Check the version text
def check_version(version):
    if not VERSION_OK.match(version):
        raise ReleaseError(f"'{version}' is not a version. Write it like 1.2.0 (or 1.2.0-rc1 for a test release).")
    return version


# Write the version into the file; returns the old version
def write_version(path, version):
    text = Path(path).read_text(encoding="utf-8")
    old = re.search(r'^__version__ = "([^"]*)"', text, re.MULTILINE)
    if not old:
        raise ReleaseError(f"Could not find the __version__ line in {path}.")
    Path(path).write_text(VERSION_LINE.sub(f'__version__ = "{version}"', text, count=1), encoding="utf-8")
    return old.group(1)


# Run a command in the project folder and stop if it fails
def run(*command, capture=False):
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=capture, encoding="utf-8")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() if capture else ""
        raise ReleaseError(f"This failed: {' '.join(command)}\n{detail}".strip())
    return (result.stdout or "").strip()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Make a new TAAS release.")
    parser.add_argument("version", help="the new version, like 1.2.0")
    parser.add_argument("--push", action="store_true", help="also upload the commit and tag to GitHub")
    args = parser.parse_args(argv)
    try:
        version = check_version(args.version)
        tag = f"v{version}"
        if run("git", "status", "--porcelain", capture=True):
            raise ReleaseError("There are changes that are not committed yet. Commit them first, then run this again.")
        if run("git", "tag", "--list", tag, capture=True):
            raise ReleaseError(f"The tag {tag} already exists. Choose a new version number.")
        old = write_version(VERSION_FILE, version)
        print(f"Version {old} -> {version}. Running the tests...")
        try:
            run(sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".")
        except ReleaseError:
            write_version(VERSION_FILE, old)  # undo, so nothing is half done
            raise
        run("git", "add", str(VERSION_FILE.relative_to(ROOT)))
        run("git", "commit", "-m", f"Release {tag}")
        run("git", "tag", "-a", tag, "-m", f"TAAS {version}")
        print(f"Committed and tagged {tag}.")
        if args.push:
            run("git", "push")
            run("git", "push", "origin", tag)
            print("Uploaded. Watch the Actions tab on GitHub: the release appears when the build finishes.")
        else:
            print("Nothing was uploaded yet. To publish, run:\n  git push\n  git push origin " + tag)
    except ReleaseError as error:
        print(f"\nStopped: {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
