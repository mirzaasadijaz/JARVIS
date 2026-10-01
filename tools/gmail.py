"""@tool send_email, search_inbox — Gmail API.

Needs GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN in .env —
run scripts/setup_gmail_oauth.py once to generate the refresh token.
"""

import base64
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from langchain_core.tools import tool

from config import settings

_service = None


def _get_service():
    global _service
    if _service is None:
        settings.require("gmail_client_id", "gmail_client_secret", "gmail_refresh_token")
        creds = Credentials(
            token=None,
            refresh_token=settings.gmail_refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.gmail_client_id,
            client_secret=settings.gmail_client_secret,
        )
        _service = build("gmail", "v1", credentials=creds)
    return _service


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email.

    Args:
        to: Recipient email address
        subject: Email subject line
        body: Plain-text email body
    """
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    _get_service().users().messages().send(userId="me", body={"raw": raw}).execute()
    return f"Sent to {to}: {subject}"


@tool
def search_inbox(query: str, max_results: int = 5) -> str:
    """Search the inbox using Gmail search syntax.

    Args:
        query: Gmail search query, e.g. "from:ahmed subject:invoice"
        max_results: Maximum number of results (default 5)
    """
    service = _get_service()
    results = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    message_ids = results.get("messages", [])
    if not message_ids:
        return "No matching emails found."

    lines = []
    for m in message_ids:
        msg = service.users().messages().get(userId="me", id=m["id"], format="metadata").execute()
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        lines.append(f"- From: {headers.get('From', '?')} | Subject: {headers.get('Subject', '?')}")
    return "\n".join(lines)
