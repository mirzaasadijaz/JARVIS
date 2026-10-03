"""Thin wrapper around the whatsapp-web.js bridge's REST API
(whatsapp_bridge/server.js). Replaces evolution_client.py — no Docker,
no Postgres, no Redis; the bridge is a single Node.js process running
alongside run_server.py.

Simpler than the Evolution API version in one real way: the bridge
includes media as base64 directly in the webhook payload, so there's no
separate "download_media" round-trip call needed here.

Every failure to deliver a message is raised as BridgeError, whose text is
written for a human ("Can't reach the WhatsApp bridge…", "923009999999 is not
registered on WhatsApp…") instead of a bare HTTP 500 and a stack trace.
"""

import base64
import binascii

import requests

from config import settings


class BridgeError(RuntimeError):
    """The WhatsApp bridge could not deliver a message.

    `status` is the bridge's HTTP status (None if it couldn't be reached) and `code`
    its machine-readable reason, e.g. "not_on_whatsapp", "no_lid", "not_ready".
    """

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


def _post(path: str, payload: dict, timeout: float, what: str) -> dict:
    settings.require("whatsapp_bridge_url")
    base = settings.whatsapp_bridge_url.rstrip("/")
    try:
        response = requests.post(f"{base}{path}", json=payload, timeout=timeout)
    except requests.exceptions.ConnectionError as exc:
        raise BridgeError(
            f"Can't reach the WhatsApp bridge at {base}. Is it running? (cd whatsapp_bridge && npm start)"
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise BridgeError(f"The WhatsApp bridge at {base} didn't answer within {timeout:.0f}s while sending {what}.") from exc
    except requests.exceptions.RequestException as exc:
        raise BridgeError(f"Couldn't talk to the WhatsApp bridge while sending {what}: {exc}") from exc

    if not response.ok:
        try:
            data = response.json()
        except ValueError:
            data = {}
        detail = (data.get("error") if isinstance(data, dict) else None) or response.text or "no details"
        detail = " ".join(str(detail).split())[:500]  # one line: error texts from WhatsApp Web contain newlines
        code = data.get("code") if isinstance(data, dict) else None
        raise BridgeError(f"WhatsApp bridge could not send {what} (HTTP {response.status_code}): {detail}", status=response.status_code, code=code)

    try:
        return response.json()
    except ValueError:
        return {}


def send_text(to: str, text: str) -> dict:
    """to: phone number in international format, no leading '+' (e.g. "923001234567"),
    or a WhatsApp chat id as received from the bridge (e.g. "…@c.us" / "…@lid").

    Raises BridgeError if the message could not be delivered."""
    # 30s: the bridge may need a few WhatsApp round-trips (see whatsapp_bridge/sender.js).
    return _post("/send-text", {"to": to, "text": text}, timeout=30, what="a text message")


def send_audio(to: str, audio_bytes: bytes, mimetype: str = "audio/ogg") -> dict:
    """Sends a voice note. audio_bytes should be OGG/Opus for best WhatsApp compatibility.

    Raises BridgeError if the voice note could not be delivered."""
    return _post(
        "/send-audio",
        {"to": to, "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"), "mimetype": mimetype},
        timeout=60,
        what="a voice note",
    )


def extract_incoming_message(webhook_payload: dict) -> dict:
    """The bridge already sends a clean, flat shape (see
    whatsapp_bridge/server.js) — this validates it and base64-decodes any
    attached media back to raw bytes.

    Raises ValueError for a payload that isn't usable. If the bridge could
    not download an attachment it sets `media_error` and sends no media —
    that is passed through (media_bytes is then absent) rather than raised, so
    the sender can be told.
    """
    if not isinstance(webhook_payload, dict):
        raise ValueError("webhook payload must be a JSON object")
    for field in ("type", "sender"):
        if not isinstance(webhook_payload.get(field), str) or not webhook_payload[field]:
            raise ValueError(f"webhook payload is missing a valid '{field}'")

    result = {
        "type": webhook_payload["type"],
        "sender": webhook_payload["sender"],
        "from_me": bool(webhook_payload.get("from_me", False)),
        "text": webhook_payload.get("text") or "",
        "media_error": webhook_payload.get("media_error"),
    }
    if webhook_payload.get("media_base64"):
        try:
            result["media_bytes"] = base64.b64decode(webhook_payload["media_base64"])
        except (binascii.Error, ValueError):
            result["media_error"] = "invalid_media"
        else:
            result["mimetype"] = webhook_payload.get("mimetype") or ""
            result["filename"] = webhook_payload.get("filename") or f"whatsapp_{result['type']}"
    return result
