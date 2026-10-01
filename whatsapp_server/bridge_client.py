"""Thin wrapper around the whatsapp-web.js bridge's REST API
(whatsapp_bridge/server.js). Replaces evolution_client.py — no Docker,
no Postgres, no Redis; the bridge is a single Node.js process running
alongside run_server.py.

Simpler than the Evolution API version in one real way: the bridge
includes media as base64 directly in the webhook payload, so there's no
separate "download_media" round-trip call needed here.
"""

import base64
import requests
from config import settings

def send_text(to: str, text: str) -> dict:
    """to: phone number in international format, no leading '+' (e.g. "923001234567")."""
    settings.require("whatsapp_bridge_url")
    response = requests.post(
        f"{settings.whatsapp_bridge_url}/send-text", json={"to": to, "text": text}, timeout=15
    )
    if response.status_code != 200:
        print(f"❌ Node.js Text Error: {response.text}")
    response.raise_for_status()
    return response.json()


def send_audio(to: str, audio_bytes: bytes, mimetype: str = "audio/ogg") -> dict:
    """Sends a voice note. audio_bytes should be OGG/Opus for best WhatsApp compatibility."""
    settings.require("whatsapp_bridge_url")
    response = requests.post(
        f"{settings.whatsapp_bridge_url}/send-audio",
        json={"to": to, "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"), "mimetype": mimetype},
        timeout=30,
    )
    if response.status_code != 200:
        print(f"❌ Node.js Audio Error: {response.text}")
    response.raise_for_status()
    return response.json()


def extract_incoming_message(webhook_payload: dict) -> dict:
    """The bridge already sends a clean, flat shape (see
    whatsapp_bridge/server.js) — this just base64-decodes any attached
    media back to raw bytes."""
    result = {
        "type": webhook_payload["type"],
        "sender": webhook_payload["sender"],
        "from_me": webhook_payload["from_me"],
        "text": webhook_payload.get("text", ""),
    }
    if "media_base64" in webhook_payload:
        result["media_bytes"] = base64.b64decode(webhook_payload["media_base64"])
        result["mimetype"] = webhook_payload.get("mimetype", "")
        result["filename"] = webhook_payload.get("filename", f"whatsapp_{result['type']}")
    return result
