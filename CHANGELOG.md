# Changelog

Newest first. The "Release TAAS.exe" workflow uses the GitHub release notes; this file is for people.

## Unreleased
- New look: a sidebar with the four steps (a tick appears when a step is done), a white card for the form, and the
  main buttons at the bottom right with a quiet **Back** next to them. Calm indigo and lavender-grey colors with the
  Ubuy yellow on the logo badge, rounded boxes and one readable font.
- **Dark mode** button in the sidebar (TAAS starts light each time). **Settings** and **Check for updates** moved to the
  sidebar; the version is shown at the bottom of it.
- A green **Looks good** appears under a web address that looks right.
- Pages that could not be read, and check warnings, now show in a soft amber instead of red. Posting errors still show
  in red.
- The first button is now called **Read my pages**. Everything else works as before.

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
