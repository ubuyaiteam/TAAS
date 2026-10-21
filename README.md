# TAAS - Tool for Automatic Article Submission (version 1.1.0)

A Windows app. You enter 2-3 web addresses and 5-10 keywords. TAAS reads the pages, writes one helpful
article with Google Gemini, lets you edit it, and posts it to your Blogger blog.

Status: all code is written and passes 257 offline tests. The live checks (Google, Gemini, Blogger) and the
.exe build still have to be done on a Windows PC. See TEST_CHECKLIST.md.

## Start from source (Windows)
    pip install -r requirements.txt
    python -m taas

## Build TAAS.exe
**Option A: on your Windows PC (Python 3.10+).** Double-click `build_exe.bat`. It runs the tests, builds `TAAS.exe`
and fills the `release` folder (TAAS.exe, USER_GUIDE.md and, if present, client_secret.json).

**Option B: in the cloud, nothing to install.** Put this project in a PRIVATE GitHub repository, open the
Actions tab, choose "Build TAAS.exe", click "Run workflow", and download the `TAAS-windows` file when it finishes.
Do not commit client_secret.json; copy it next to TAAS.exe yourself afterwards.
Neither option has been run yet; the build environment used to write the code is not Windows.

## Commands
| What | Command |
| --- | --- |
| Install libraries | `pip install -r requirements.txt` |
| Start the app | `python -m taas` (or `python run_taas.py`) |
| Build the .exe | `build_exe.bat` |
| Run all offline tests | `python -m unittest discover -s tests -t . -v` |
| Live check: sign in, list blogs, draft test post | `python phase1_check.py` |
| Same, with 1-3 links | `python phase1_check.py --link "anchor=https://address"` |
| Same, publish live | `python phase1_check.py --live` |
| Switch Google account | `python phase1_check.py --switch-account` |
| Live check: pages, detection, article | `python phase23_check.py --url URL1 --url URL2 --keywords "k1, k2, k3, k4, k5"` |
| Same, also save a Blogger draft | add `--post-draft` |
| Make a release (bump version, test, commit, tag) | `python release.py 1.2.0` (add `--push` to upload). See RELEASING.md |
| Sign out by hand (Command Prompt) | `del %APPDATA%\TAAS\token.json` |
| Open the settings folder | `explorer %APPDATA%\TAAS` |

## Files
| File | Purpose |
| --- | --- |
| RELEASING.md | How to publish a new version and how the in-app update notice works |
| CHANGELOG.md | What changed in each version |
| release.py | Makes a release: bumps the version, runs the tests, commits and tags |
| GOOGLE_SETUP.md | One-time Google Cloud setup (admin) |
| USER_GUIDE.md | Guide for the SEO team |
| TEST_CHECKLIST.md | Live test steps and sign-off |
| taas/ | The code: config, auth, blogger, gemini, pagereader, detect, anchors, article, checks, editor, safeguards, workflow, ui/ |
| tests/ | 257 offline tests (screen tests use a stand-in toolkit, see tests/stub_ctk.py) |

## Settings (.env in %APPDATA%\TAAS)
    GEMINI_API_KEY=your key
    GEMINI_MODEL=gemini-3.5-flash-lite    (change it if Google says the model is not found)
    MIN_WORDS=300
    MAX_WORDS=400
    POST_LIMIT_PER_DAY=                   (empty = no limit)
    UPDATE_REPO=owner/name                (optional: overrides the repository in taas/updates.py)
    UPDATE_TOKEN=                         (optional: read-only token, only if the repository is private)
The Google client file `client_secret.json` is looked for in this order: the path in GOOGLE_CLIENT_SECRET_FILE,
the TAAS settings folder, then next to the app.

## What is kept on the computer
.env (Gemini key and settings), token.json (Google sign-in token, no password), post_log.json (time, blog and
addresses of recent posts, no article text). No key is built into the .exe.
