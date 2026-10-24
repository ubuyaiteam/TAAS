# TAAS user guide

TAAS writes one helpful article from your web addresses and keywords, lets you read and edit it,
and posts it to your Blogger blog. Nothing is posted until you confirm.

## Before you start (once)
1. Keep `TAAS.exe` and `client_secret.json` in the same folder. (Your admin gives you both.)
2. You need an API key for **Gemini or OpenAI** and a **Google account that owns a Blogger blog**.
3. Your Google address must be added as a test user by your admin (see GOOGLE_SETUP.md).

## First run: Setup screen
1. Choose **Gemini** or **OpenAI** from the AI provider drop-down. Enter that provider's API key and model
   (the default model is prefilled). Click **Save settings**.
2. Click **Sign in with Google**. Your browser opens. Choose your account and allow access.
   TAAS never sees your Google password.
3. Click **Load my blogs** and choose your blog.
4. Click **Continue**.

You can open Setup at any time with **Settings** at the bottom of the left sidebar.

## Writing an article
**Step 1: Add pages.**
The screen starts with one web address field. Click **+ Add another URL** to add more fields (up to 3 total); enter at least 2 addresses. A green **Looks good** appears when one looks right; each address must start with `http://` or `https://`. Each address becomes one link.
Enter 5 to 10 keywords, one per line or separated by commas. Click **Read my pages**.

**Step 2: Check details.**
TAAS shows the brand, category and country it found. Correct anything wrong. If a page could not be read,
type the details yourself. Brand names are only used to keep them out of the article.
Click **Write the article** (this takes a minute or two).

**Step 3: Review article.**
- Read the article. Edit the title and text freely.
- `[square brackets]` mark a link. Start a line with `##` for a subheading and with `-` for a list item.
  Leave an empty line between paragraphs.
- Under **Images** you can add pictures. Blogger cannot take files from TAAS, so the picture must already be on the
  internet (for example on your own website). Paste its web address and a short description of what it shows, click in
  the article where it should go, then click **Add image**. It appears as a line like
  `{image: https://... | description}` after the paragraph you clicked in. Delete that line to remove the picture.
  Pictures do not count as words, and a description is needed so the checks pass. Do not put a brand name in it.
  The button **Generate images automatically** is not available yet.
- Under **Links**, choose a different keyword as the link text for an address if you want.
- **Check again** re-runs the checks. They only warn you; they never block posting.
- **Write it again** replaces the text with a new article.
- Under **Post to Blogger** choose **Save as Blogger draft** (safe) or **Publish live**,
  tick the confirmation box, then click **Post to Blogger**.

**Step 4: Publish.** You get the link to your post. Use **Copy link** or **Open in browser**.

## Updates
The sidebar shows the version you are running and which of the four steps you are on. **Dark mode** (bottom of the
sidebar) switches to a dark look; TAAS starts light each time. When TAAS starts it quietly looks for a newer version, and shows
**New version X is available** with an **Open download page** button if there is one. You can also click
**Check for updates** at any time. To update, download the new `TAAS.exe` from the page that opens and replace the
old one. Your settings and sign-in stay, because they are kept in `%APPDATA%\TAAS`, not in the .exe.

## Good to know
- Articles are about 300 to 400 words by default. Change this in Setup.
- The optional **posting limit** counts live posts to the same blog in the last 24 hours. Drafts do not count.
- TAAS warns you if you use the same addresses again within 7 days. Many near-identical posts that all link to the same
  sites can look like spam to Google.
- Google decides what gets indexed. TAAS writes a useful, unique article, but it cannot promise indexing.

## Messages you may see
| Message | What to do |
| --- | --- |
| Google client file not found | Put `client_secret.json` next to `TAAS.exe`. |
| Google access expired or was revoked. Please sign in again. | Open Setup and click **Use another Google account** or **Sign in with Google**. |
| Gemini or OpenAI did not accept the API key | Check the selected provider's key in Setup. |
| The selected provider's model was not found | Ask your admin for the right model name and enter it in Setup. |
| ... does not allow automatic reading (HTTP 403) | That website blocks tools. Type the details by hand. |
| The article still has N check problem(s) | Read the list, fix the text, click **Check again**. You may still post. |
| Update checking is not set up yet | Ask the person who maintains TAAS to set the GitHub repository (see RELEASING.md). |
| GitHub found no published release ... | No release is published yet, or the repository is private and needs `UPDATE_TOKEN`. |
| Posting limit reached | Change the limit in Setup, or save as a draft. |

## Where TAAS keeps files
Folder `%APPDATA%\TAAS` (type that in the Windows Explorer address bar):
- `.env`: your selected provider, Gemini/OpenAI keys and settings (and, if your admin set them, `UPDATE_REPO` / `UPDATE_TOKEN` for update checks).
- `token.json`: your Google sign-in token (not your password).
- `post_log.json`: time, blog and addresses of recent posts, used for the limit and repeat warning. No article text.

To sign out, use **Use another Google account** in Setup, or delete `token.json`.
To remove everything, delete the `TAAS` folder and `TAAS.exe`.
