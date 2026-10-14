A [Flask](https://flask.palletsprojects.com/en/stable/) app that provides connection between a few key services at NSPS. The core is a website that:
* requires login with your Slack account
* lists the files on the NSPS Google Drive account to logged in users
* allows logged in users to download files from the NSPS Google Drive

Users themselves do not need to create a Google Drive account and only get read only access to the Google Drive. Folders on the Google Drive are supported and when downloading, it chunks the files through the Flask app back to the users. To run this you will need a recent version of Python (3.9 or greater):

### Setup

Create an `.env` file in the root directory

Set a `FLASK_SECRET_KEY` in the `.env` and enter a nice long random string as it's value.

You will need to create a [Slack app](https://docs.slack.dev/) that allows a user to use the OAuth flow to login.  that contains:

```
SLACK_CLIENT_ID=...
SLACK_CLIENT_SECRET=...
SLACK_REDIRECT_URI=...
```

The values for `CLIENT_ID` and `CLIENT_SECRET` can be pulled from the Slack user interface. The `REDIRECT_URI` is set in the Slack site and matches the redirect back to this site. If the server you running this on is not accessible from the internet, you might need to us a tool like [localtunnel](https://github.com/localtunnel/localtunnel).

You will need to allow a service account on the [Google Cloud API](https://console.cloud.google.com/) to read the Google Drive you'd like to access. That will create a `service-account.json` that you can download and place in the root directory.

Then add in the folder id for the Google Drive you'd like to access into the `.env`:

```
GOOGLE_DRIVE_FOLDER_ID=...
```

At the end you of setup, in the same directory as this `README.md` you should have:

1. an `.env` containing values for `FLASK_SECRET_KEY`, `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, `SLACK_REDIRECT_URI` and `GOOGLE_FOLDER_ID`

### Running

```
python -m venv .venv
pip install -r requirements.txt
python app.py
```

That's it. Since this app maintains no state or information, it can be run on any server that allows Python to run.

