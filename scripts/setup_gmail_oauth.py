"""One-off — run this once to complete the Gmail OAuth flow and get a
refresh token for .env. Opens a browser window to sign in and consent.

Run from the project root:
    python scripts/setup_gmail_oauth.py
"""

import sys
from pathlib import Path

# Running this file directly only puts scripts/ on sys.path, not the
# project root where config.py lives — same fix needed anywhere a file
# in a subfolder imports from the root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google_auth_oauthlib.flow import InstalledAppFlow

from config import settings

SCOPES = ["https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.readonly"]


def main() -> None:
    settings.require("gmail_client_id", "gmail_client_secret")
    client_config = {
        "installed": {
            "client_id": settings.gmail_client_id,
            "client_secret": settings.gmail_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=0)

    print("\nAdd this to your .env:")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")


if __name__ == "__main__":
    main()
