# Changelog

Newest first. The "Release TAAS.exe" workflow uses the GitHub release notes; this file is for people.

## 1.1.0
- Pictures in articles: a new **Images** section on the article screen. Paste a picture address and a description,
  click **Add image**. Pictures are checked (address, description, no brand names in the description).
- Button **Generate images automatically** is shown but not clickable yet (planned).
- Version number shown in the top bar and the window title.
- **Check for updates** button, and a quiet check at start-up that shows a notice when a newer version is released.
- Releases through Git: `release.py` makes the version commit and tag; pushing the tag builds `TAAS.exe` on GitHub and
  publishes it as a Release (workflow `release.yml`).
- Added `.gitignore` (keeps `client_secret.json`, `.env`, `token.json` out of Git).

## 1.0.0-rc1
- First complete version: read pages, write the article with Gemini, edit, check, post to Blogger.
