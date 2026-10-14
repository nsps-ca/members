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
Clicking a file name downloads it through the app.

## Run with supervisord (gunicorn)

`python app.py` is the development server. For anything long-lived, [supervisorctl.conf](supervisorctl.conf)
runs the app under gunicorn and keeps it alive:

```sh
pip install -r requirements.txt          # includes gunicorn and supervisor
.venv/bin/supervisord -c supervisorctl.conf
.venv/bin/supervisorctl -c supervisorctl.conf status
```

Common controls (all take `-c supervisorctl.conf`):

```sh
.venv/bin/supervisorctl -c supervisorctl.conf restart members   # reload after a code change
.venv/bin/supervisorctl -c supervisorctl.conf stop members
.venv/bin/supervisord -c supervisorctl.conf                      # start (daemonizes)
.venv/bin/supervisorctl -c supervisorctl.conf shutdown           # stop supervisord itself
```

Gunicorn listens on `127.0.0.1:8000`, the port used above, and is started from this directory so
`app.py` picks up `.env` on its own. Change `--bind` to `0.0.0.0:8000` to reach it from another
host, and raise `--workers`/`--threads` for more concurrency. It runs `gthread` workers because
those keep sending heartbeats mid-request, so gunicorn's worker timeout cannot kill a long Drive
download part-way through. `logs/gunicorn.log` holds the gunicorn output (including access logs)
and `logs/supervisord.log` the supervisor output; both are rotated at 10 MB.

> The `__main__` block's cookie settings (`SESSION_COOKIE_SAMESITE="None"`,
> `SESSION_COOKIE_SECURE=True`) only apply to `python app.py`. Under gunicorn the defaults are
> used, which is fine for the `https://` tunnel in `SLACK_REDIRECT_URI`, but if you terminate
> HTTPS in front of gunicorn on another host, set those in the app config so the session cookie
> keeps its `Secure` flag.

> `SLACK_REDIRECT_URI` must exactly match the redirect URL registered in the Slack app.
> Note that `app.py`'s `__main__` block sets `SESSION_COOKIE_SECURE=True`, which drops the
> session cookie over plain `http://` — remove that line (or serve over HTTPS) if login
> appears to succeed but `/files` still redirects to `/?m=unauth`.

## Files

- [app.py](app.py) — routes: `/`, `/login`, `/callback`, `/files`, `/files/<id>/download`, `/logout`
- [templates/index.html](templates/index.html) — Bootstrap login/profile card
- [templates/files.html](templates/files.html) — Bootstrap table of Drive files

## Downloading

`GET /files/<id>/download` is login-gated and streams the file back with
`Content-Disposition: attachment`:

- Regular files are fetched with `files.get_media`.
- Google Workspace files (Docs/Sheets/Slides/Drawings) are exported to PDF, XLSX or PNG,
  since they have no bytes of their own.
- When `GOOGLE_DRIVE_FOLDER_ID` is set, files outside that folder are refused with a 403,
  so a logged-in user can only reach what the listing shows.

Downloads are streamed in 4 MB chunks (`CHUNK_SIZE`) rather than buffered, so memory use
stays flat and multi-GB files work. `MediaIoBaseDownload` fetches each chunk with a Range
request and retries transient failures up to three times, and the chunk is handed to the
client before the next one is requested, which gives natural backpressure.

`Content-Length` is sent for regular files (so browsers show progress and can detect a
short read). A crash part-way through the body can only be logged and truncated, since the
headers are already on the wire.
