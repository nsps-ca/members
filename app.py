import os
import secrets
from urllib.parse import urlencode
from functools import wraps
import requests
from flask import Flask, redirect, render_template, request, session, url_for

AUTHORIZE_URL = "https://slack.com/openid/connect/authorize"
TOKEN_URL = "https://slack.com/api/openid.connect.token"
USERINFO_URL = "https://slack.com/api/openid.connect.userInfo"

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

load_dotenv()

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

CLIENT_ID = os.getenv("SLACK_CLIENT_ID")
CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET")
SLACK_REDIRECT_URI = os.getenv("SLACK_REDIRECT_URI")
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
assert CLIENT_ID
assert CLIENT_SECRET


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user") is None:
            return redirect("/?m=unauth")
        return f(*args, **kwargs)
    return decorated_function

@app.get("/")
def index():
    return render_template("index.html", user=session.get("user"))


@app.get("/login")
def login():
    session.clear()
    session["state"] = state = secrets.token_urlsafe(24)
    params = {
        "response_type": "code",
        "scope": "openid profile email",
        "client_id": CLIENT_ID,
        "redirect_uri": SLACK_REDIRECT_URI,
        "state": state,
        "team": "T0ABMM43WPL",
    }
    return redirect(f"{AUTHORIZE_URL}?{urlencode(params)}")


@app.get("/callback")
def callback():
    if request.args.get("error"):
        return redirect(f"/?m={request.args.error}")

    if request.args.get("state") != session.pop("state", None):
        return redirect(f"/?m=login-error")

    token = requests.post(
        TOKEN_URL,
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": request.args.get("code"),
            "redirect_uri": SLACK_REDIRECT_URI,
        },
        timeout=10,
    ).json()
    if not token.get("ok"):
        return redirect(f"/?m={token.get.error}")

    info = requests.get(
        USERINFO_URL,
        headers={"Authorization": f"Bearer {token['access_token']}"},
        timeout=10,
    ).json()
    if not info.get("ok"):
        return redirect(f"/?m={info.get['error']}")

    session["user"] = {
        "name": info.get("name") or info.get("email") or "Slack user",
        "email": info.get("email"),
        "picture": info.get("picture"),
        "team_id": info.get("https://slack.com/team_id"),
        "user_id": info.get("https://slack.com/user_id"),
    }
    return redirect(url_for("listing"))

@app.get("/files")
@login_required
def listing():
    if not GOOGLE_SERVICE_ACCOUNT_FILE or not os.path.isfile(GOOGLE_SERVICE_ACCOUNT_FILE):
        return "GOOGLE_SERVICE_ACCOUNT_FILE is not set or does not exist", 500

    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_SERVICE_ACCOUNT_FILE, scopes=DRIVE_SCOPES
    )
    drive = build("drive", "v3", credentials=credentials, cache_discovery=False)

    query = "trashed = false"
    if GOOGLE_DRIVE_FOLDER_ID:
        query = f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and {query}"

    files, page_token = [], None
    try:
        while True:
            page = (
                drive.files()
                .list(
                    q=query,
                    pageSize=100,
                    pageToken=page_token,
                    orderBy="modifiedTime desc",
                    fields="nextPageToken, files(id, name, mimeType, modifiedTime, size, webViewLink)",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
            files += page.get("files", [])
            page_token = page.get("nextPageToken")
            if not page_token:
                break
    except HttpError as e:
        return f"Google Drive error: {e}", 502

    return render_template("files.html", user=session.get("user"), files=files)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.config.update(SESSION_COOKIE_SAMESITE="None", SESSION_COOKIE_SECURE=True)
    app.run(debug=True, port=8000, host="localhost")
