# Releasing a new version

## One-time setup
1. Open `taas/updates.py` and set `DEFAULT_REPO = "your-github-name/your-repo-name"`. (Or put
   `UPDATE_REPO=owner/name` in the `.env` of a computer to override it.) Commit this.
2. On GitHub: Settings > Actions > General > Workflow permissions: allow **Read and write permissions**
   (the release workflow needs it to publish a release).
3. Private repository? GitHub hides its releases from anyone who is not signed in, so the update check in the app
   gets "not found". Choose one:
   - Make the repository public (do not commit `client_secret.json`, `.env` or `token.json`; `.gitignore` already
     excludes them), or
   - Give each computer a **read-only** GitHub token (fine-grained token, this repository only, permission
     "Contents: read") as `UPDATE_TOKEN=...` in `%APPDATA%\TAAS\.env`. Anyone with that file can use the token, so
     keep its permission minimal.

## Every release
1. Make and commit your changes locally. Run the tests: `python -m unittest discover -s tests -t .`
2. Add a short entry to `CHANGELOG.md` and commit it.
3. Run `python release.py 1.2.0` (use your new number). It checks that everything is committed, changes the version
   in `taas/__init__.py`, runs the tests, commits "Release v1.2.0" and creates the tag `v1.2.0`.
4. Upload: `git push` then `git push origin v1.2.0` (or run step 3 with `--push`).
5. On GitHub, the **Actions** tab shows "Release TAAS.exe" running. When it is green, the **Releases** page has
   `TAAS.exe` and `USER_GUIDE.md`. Copy `client_secret.json` next to the downloaded `TAAS.exe` yourself, as before.

## What users see
- A running TAAS asks GitHub for the latest release when it starts, and when the user clicks **Check for updates**.
- If the latest release number is higher than the version in the app, the top bar shows
  "New version X is available" and a button that opens the release page.
- Version numbers: `1.2.0` is a normal release. `1.2.0-rc1` (with a dash) is published as a **pre-release** and users
  are NOT told about it, so you can test the build first. The next normal release `1.2.0` then counts as newer.

## If something goes wrong
- The workflow stops with "The tag is ... but taas/__init__.py says ...": the tag was made by hand. Delete the tag
  (`git tag -d v1.2.0` and `git push origin :refs/tags/v1.2.0`) and use `release.py`.
- The tests fail on GitHub: nothing is published. Fix, then make a new version number.
