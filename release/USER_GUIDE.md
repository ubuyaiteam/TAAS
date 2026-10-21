# TAAS user guide

TAAS writes one helpful article from your web addresses and keywords, lets you read and edit it,
and posts it to your Blogger blog. Nothing is posted until you confirm.

## Before you start (once)
1. Keep `TAAS.exe` and `client_secret.json` in the same folder. (Your admin gives you both.)
2. You need your own **Gemini API key** and a **Google account that owns a Blogger blog**.
3. Your Google address must be added as a test user by your admin (see GOOGLE_SETUP.md).

## First run: Setup screen
1. Paste your Gemini API key. Leave the model as it is unless your admin says otherwise. Click **Save settings**.
2. Click **Sign in with Google**. Your browser opens. Choose your account and allow access.
   TAAS never sees your Google password.
3. Click **Load my blogs** and choose your blog.
4. Click **Continue**.

You can open Setup at any time with the **Setup** button (top right).

## Writing an article
**Step 1: Addresses and keywords.**
Enter 2 or 3 web addresses (each must start with `http://` or `https://`). Each address becomes one link.
Enter 5 to 10 keywords, one per line or separated by commas. Click **Read the pages**.

**Step 2: Check the details.**
TAAS shows the brand, category and country it found. Correct anything wrong. If a page could not be read,
type the details yourself. Brand names are only used to keep them out of the article.
Click **Write the article** (this takes a minute or two).

**Step 3: Read, edit and post.**
- Read the article. Edit the title and text freely.
- `[square brackets]` mark a link. Start a line with `##` for a subheading and with `-` for a list item.
  Leave an empty line between paragraphs.
- Under **Links**, choose a different keyword as the link text for an address if you want.
- **Check again** re-runs the checks. They only warn you; they never block posting.
- **Write it again** replaces the text with a new article.
- Under **Post to Blogger** choose **Save as Blogger draft** (safe) or **Publish live**,
  tick the confirmation box, then click **Post to Blogger**.

**Step 4: Result.** You get the link to your post. Use **Copy link** or **Open in browser**.

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
| Gemini did not accept the API key | Check the key in Setup. |
| The Gemini model ... was not found | Ask your admin for the right model name and enter it in Setup. |
| ... does not allow automatic reading (HTTP 403) | That website blocks tools. Type the details by hand. |
| The article still has N check problem(s) | Read the list, fix the text, click **Check again**. You may still post. |
| Posting limit reached | Change the limit in Setup, or save as a draft. |

## Where TAAS keeps files
Folder `%APPDATA%\TAAS` (type that in the Windows Explorer address bar):
- `.env`: your Gemini key and settings.
- `token.json`: your Google sign-in token (not your password).
- `post_log.json`: time, blog and addresses of recent posts, used for the limit and repeat warning. No article text.

To sign out, use **Use another Google account** in Setup, or delete `token.json`.
To remove everything, delete the `TAAS` folder and `TAAS.exe`.
