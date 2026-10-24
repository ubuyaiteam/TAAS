# Google Cloud setup for TAAS (done once)

TAAS signs users in with Google (OAuth). Nobody types a Google password into the tool.
Someone creates one Google Cloud project, and the same client file is used by all users.
Menu names in Google Cloud Console change from time to time, so follow the intent of each step.

1. Go to https://console.cloud.google.com and sign in with a Google account.
2. Create a new project (for example "TAAS").
3. In the project, open **APIs & Services > Library**, search for **Blogger API v3** and click **Enable**.
4. Open the **OAuth consent screen** (shown as "Google Auth Platform" in newer consoles) and set it up:
   - App name: TAAS. Add a support email and a developer contact email.
   - Audience / user type: **External**.
5. While the app is in **Testing** status, add every user's Google address under **Test users**.
   Only listed test users can sign in.
6. Open **Clients** (or **Credentials > Create credentials > OAuth client ID**):
   - Application type: **Desktop app**. Name: TAAS Desktop.
   - Click **Download JSON**.
7. Save the downloaded file as `client_secret.json` in the TAAS folder:
   - Windows: `%APPDATA%\TAAS\client_secret.json`
   - or put it next to `TAAS.exe`. For a release, copy it into the project folder before running `build_exe.bat`, and it is copied into the `release` folder.
   - or put the file anywhere and set `GOOGLE_CLIENT_SECRET_FILE=<full path>` in the TAAS `.env` file.
8. Run `python phase1_check.py` (see README.md).

## Things to confirm in Google's own documentation

- As I understand Google's rules, a refresh token issued while an External app is in Testing status
  can expire after 7 days, which would make users sign in again every week. Publishing the app
  (status "In production") is the usual way around that, and it may show an "unverified app" screen
  to users. Please confirm the current rules in the Google Cloud console and documentation before
  choosing between Testing and In production.
- The Blogger scope used by TAAS is https://www.googleapis.com/auth/blogger.
