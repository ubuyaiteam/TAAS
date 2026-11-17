# TAAS - Tool for Automatic Article Submission (version 2.4.0)

A Windows app. You enter at least 1 (up to 5) web addresses and 5-10 keywords. TAAS reads the pages, writes one helpful
article with Google Gemini or OpenAI, lets you edit it, and posts it to your Blogger blog.

Run the offline test suite with the command below. Live Google, AI provider, and Blogger checks require
configured credentials; see TEST_CHECKLIST.md.

## Start from source (Windows)
    pip install -r requirements.txt
    python -m taas

## Build TAAS.exe
**Option A: on your Windows PC (Python 3.10+ and Inno Setup 6.3+).** Double-click `build_exe.bat`. It prepares
a local environment, runs the tests, builds `dist\TAAS.exe`, refreshes `release\USER_GUIDE.md`, and creates a
versioned installer. The local executable embeds the project-root `client_secret.json` and copies it into
`%APPDATA%\TAAS` the first time it runs. Anyone who receives this executable can extract the client file.

**Option B: in the cloud, nothing to install.** Put this project in a PRIVATE GitHub repository, open the
Actions tab, choose "Build TAAS.exe", click "Run workflow", and download the `TAAS-windows` artifact when it finishes.
It contains `TAAS.exe` and `USER_GUIDE.md`, but not `client_secret.json`, so it cannot install that file automatically.
Do not commit the client file; add it to `%APPDATA%\TAAS` before signing in when using this artifact.

## Commands
| What | Command |
| --- | --- |
| Install libraries | `pip install -r requirements.txt` |
| Start the app | `python -m taas` (or `python run_taas.py`) |
| Build the .exe | `build_exe.bat` |
| Run all offline tests | `python -m unittest discover -s tests -t . -v` |
| Live check: sign in, list blogs, draft test post | `python phase1_check.py` |
| Same, with 1-5 links | `python phase1_check.py --link "anchor=https://address"` |
| Same, publish live | `python phase1_check.py --live` |
| Switch Google account | `python phase1_check.py --switch-account` |
| Live check: pages, detection, article | `python phase23_check.py --url URL1 --url URL2 --keywords "k1, k2, k3, k4, k5"` |
| Same, also save a Blogger draft | add `--post-draft` |
| Make a release (bump version, test, commit, tag) | `python release.py 2.4.0` (add `--push` to upload). See RELEASING.md |
| Sign out by hand (Command Prompt) | `del %APPDATA%\TAAS\token.json` |
| Open the settings folder | `explorer %APPDATA%\TAAS` |

## Files
| File | Purpose |
| --- | --- |
| RELEASING.md | How to publish a new version and how the in-app update notice works |
| CHANGELOG.md | What changed in each version |
| assets/taas-logo.ico | The multi-size Windows app and installer icon |
| release.py | Makes a release: bumps the version, runs the tests, commits and tags |
| GOOGLE_SETUP.md | One-time Google Cloud setup (admin) |
| USER_GUIDE.md | Guide for the SEO team |
| TEST_CHECKLIST.md | Live test steps and sign-off |
| taas/ | The code: config, auth, blogger, gemini, pagereader, detect, anchors, article, checks, editor, safeguards, workflow, ui/ |
| tests/ | 300 offline tests (screen tests use a stand-in toolkit, see tests/stub_ctk.py) |

## Settings (.env in %APPDATA%\TAAS)
    AI_PROVIDER=gemini                 (gemini or openai; also selectable in Setup)
    GEMINI_API_KEY=your key
    GEMINI_MODEL=gemini-3.5-flash-lite    (change it if Google says the model is not found)
    OPENAI_API_KEY=your key
    OPENAI_MODEL=gpt-4o-mini
    MIN_WORDS=300
    MAX_WORDS=400
    POST_LIMIT_PER_DAY=                   (empty = no limit)
    UPDATE_REPO=owner/name                (optional: overrides the repository in taas/updates.py)
    UPDATE_TOKEN=                         (optional: read-only token, only if the repository is private)
The Google client file `client_secret.json` is looked for in this order: the path in GOOGLE_CLIENT_SECRET_FILE,
the TAAS settings folder, next to the app, then inside a bundled executable.

Cloudinary image uploads read `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and `CLOUDINARY_API_SECRET`
from `.env` next to the app (the project folder when running from source).

## What is kept on the computer
.env (AI provider keys and settings), token.json (Google sign-in token, no password), post_log.json (time, blog and
addresses of recent posts, no article text). User API keys are not built into the .exe. A local build embeds
`client_secret.json`; cloud builds do not.
