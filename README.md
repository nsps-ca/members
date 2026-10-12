# Slack login demo

Minimal Flask app that signs users in with Slack (OpenID Connect), shows their profile, and
lists files from a Google Drive via a service account.

## Setup

### Slack

1. Create a Slack app at <https://api.slack.com/apps> ("From scratch").
2. Under **OAuth & Permissions → Redirect URLs**, add your callback URL, e.g. `http://localhost:8000/callback`.
3. Under **User Token Scopes**, add `openid`, `profile`, `email`.
4. Copy the **Client ID** and **Client Secret** from **Basic Information**.

### Google Drive (service account)

1. In the Google Cloud Console, create (or pick) a project and **enable the Google Drive API**.
2. **IAM & Admin → Service Accounts → Create service account**, then open it and add a
   **JSON key** (Keys → Add key → Create new key → JSON). Download the file.
3. Point `GOOGLE_SERVICE_ACCOUNT_FILE` at that JSON file.
4. Copy the service account's email address (`...@...iam.gserviceaccount.com`) and **share the
   Drive folder** you want to list with it as **Viewer**. A service account only sees files
   that are shared with it.
5. Optionally set `GOOGLE_DRIVE_FOLDER_ID` to list just that folder. Find it in the folder's
   URL: `https://drive.google.com/drive/folders/<FOLDER_ID>`. If unset, all files visible to
   the service account are listed.

## Configure

Create a `.env` file (loaded automatically by `python-dotenv`):

```sh
FLASK_SECRET_KEY=...
SLACK_CLIENT_ID=...
SLACK_CLIENT_SECRET=...
SLACK_REDIRECT_URI=http://localhost:8000/callback
GOOGLE_SERVICE_ACCOUNT_FILE=/absolute/path/to/service-account.json
GOOGLE_DRIVE_FOLDER_ID=
```

## Run

```sh
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open <http://localhost:8000> and click **Sign in with Slack**, then **Browse Drive files**.

> `SLACK_REDIRECT_URI` must exactly match the redirect URL registered in the Slack app.
> Note that `app.py`'s `__main__` block sets `SESSION_COOKIE_SECURE=True`, which drops the
> session cookie over plain `http://` — remove that line (or serve over HTTPS) if login
> appears to succeed but `/files` still redirects to `/?m=unauth`.

## Files

- [app.py](app.py) — routes: `/`, `/login`, `/callback`, `/files`, `/logout`
- [templates/index.html](templates/index.html) — Bootstrap login/profile card
- [templates/files.html](templates/files.html) — Bootstrap table of Drive files
