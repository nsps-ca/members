import io
import os
import secrets
from itertools import chain
from urllib.parse import quote, urlencode
from functools import wraps
import requests
from flask import (
    Flask,
    Response,
    abort,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

AUTHORIZE_URL = "https://slack.com/openid/connect/authorize"
TOKEN_URL = "https://slack.com/api/openid.connect.token"
USERINFO_URL = "https://slack.com/api/openid.connect.userInfo"

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

load_dotenv()

DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

CHUNK_SIZE = 4 * 1024 * 1024

DOWNLOAD_EXPORTS = {
    "application/vnd.google-apps.document": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.drawing": ("image/png", ".png"),
}

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

SLACK_TEAM = "T0ABMM43WPL"
CLIENT_ID = os.getenv("SLACK_CLIENT_ID")
CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET")
SLACK_REDIRECT_URI = os.getenv("SLACK_REDIRECT_URI")
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

assert app.secret_key, "FLASK_SECRET_KEY is not defined"
assert CLIENT_ID, "SLACK_CLIENT_ID is not defined"
assert CLIENT_SECRET, "SLACK_CLIENT_SECRET is not defined"
assert SLACK_REDIRECT_URI, "SLACK_REDIRECT_URI is not defined"
assert GOOGLE_SERVICE_ACCOUNT_FILE, "GOOGLE_SERVICE_ACCOUNT_FILE is not defined"


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user") is None:
            return redirect("/?m=unauth")
        return f(*args, **kwargs)

    return decorated_function


def drive_service():
    if not GOOGLE_SERVICE_ACCOUNT_FILE or not os.path.isfile(GOOGLE_SERVICE_ACCOUNT_FILE):
        abort(500, "GOOGLE_SERVICE_ACCOUNT_FILE is not set or does not exist")

    credentials = service_account.Credentials.from_service_account_file(
        GOOGLE_SERVICE_ACCOUNT_FILE, scopes=DRIVE_SCOPES
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def drive_chunks(media_request, chunksize=CHUNK_SIZE, num_retries=3):
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, media_request, chunksize=chunksize)
    done = False
    while not done:
        _, done = downloader.next_chunk(num_retries=num_retries)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate()


SIZE_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def human_size(size, precision=1):
    """Format a byte count for display, e.g. "1536" -> "1.5 KB"."""
    try:
        value = float(size)
    except (TypeError, ValueError):
        return "—"
    if value < 0:
        return "—"

    for unit in SIZE_UNITS:
        if value < 1024 or unit == SIZE_UNITS[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.{precision}f} {unit}"
        value /= 1024


app.jinja_env.filters["human_size"] = human_size


def attachment_header(name):
    # quote() percent-encodes CR/LF, so a hostile filename can't forge headers.
    fallback = "".join(c for c in name if c.isascii() and c.isprintable() and c not in '"\\')
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name, safe='')}"


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
        "team": SLACK_TEAM,
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
    drive = drive_service()

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
                    fields="nextPageToken, files(id, name, mimeType, modifiedTime, size)",
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


@app.get("/files/<file_id>/download")
@login_required
def download(file_id):
    drive = drive_service()

    try:
        meta = (
            drive.files()
            .get(
                fileId=file_id,
                fields="id, name, mimeType, parents",
                supportsAllDrives=True,
            )
            .execute()
        )
    except HttpError as e:
        return f"Google Drive error: {e}", 404 if e.resp.status == 404 else 502

    # Never serve anything outside the folder we list.
    if GOOGLE_DRIVE_FOLDER_ID and GOOGLE_DRIVE_FOLDER_ID not in meta.get("parents", []):
        return "File is not in the configured folder", 403

    name, mime = meta["name"], meta["mimeType"]
    if mime.startswith("application/vnd.google-apps."):
        export_mime, extension = DOWNLOAD_EXPORTS.get(mime, (None, None))
        if not export_mime:
            return f"Files of type {mime} cannot be downloaded", 400
        media_request = drive.files().export_media(fileId=file_id, mimeType=export_mime)
        mime, name, size = export_mime, name + extension, None
    else:
        media_request = drive.files().get_media(fileId=file_id, supportsAllDrives=True)
        size = meta.get("size")

    chunks = drive_chunks(media_request)
    try:
        # Pull the first chunk now so Drive errors still produce a clean status code
        # instead of a truncated body part-way through the response.
        first = next(chunks, b"")
    except HttpError as e:
        return f"Google Drive error: {e}", 502

    def remainder():
        try:
            yield from chunks
        except HttpError as e:
            # The response has already started, so all we can do is log it and end the
            # body; Content-Length then tells the client the file is incomplete.
            app.logger.warning("Download of %s broke off: %s", file_id, e)

    headers = {"Content-Disposition": attachment_header(name)}
    if size:
        headers["Content-Length"] = size
    return Response(chain([first], remainder()), mimetype=mime, headers=headers)


@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.config.update(SESSION_COOKIE_SAMESITE="None", SESSION_COOKIE_SECURE=True)
    app.run(debug=True, port=8000, host="localhost")
