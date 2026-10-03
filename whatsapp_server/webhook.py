"""FastAPI app + /webhook route — receives events from the whatsapp-web.js
bridge (whatsapp_bridge/server.js), not Evolution API.

Document/image attachments, from anyone: ingested into the RAG
store (tools/documents.py) so their contents become searchable.

Smart Replies:
- If a user sends a text, Jarvis replies with text.
- If a user sends a voice note, Jarvis replies with a voice note.
- If ElevenLabs fails or its API limit is reached (429), Jarvis automatically falls back to text.

Reliability rules (the reason this file looks the way it does):
- /webhook only validates and queues. Everything slow (speech-to-text, the LLM,
  OCR, talking to the bridge) runs in a background task, so the bridge always
  gets its 200 quickly and one slow message can't block the others.
- A background task has no caller to raise to — an exception there only dumps a
  traceback into the server log (the "Exception in ASGI application" you saw).
  So every task catches everything, logs ONE readable line, and — when the
  failure was on Jarvis's side — tells the sender instead of going silent.
- Messages from the same sender are handled one at a time, so quick back-to-back
  messages can't run on the same conversation thread concurrently.
"""

import json
import logging
import os
import re
import shutil
import tempfile
import threading

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from config import settings
from core.agent import agent
from core.runner import ask_jarvis
from tools.documents import ingest_file
from voice.stt import transcribe
from voice.tts import synthesize_speech
from whatsapp_server.bridge_client import BridgeError, extract_incoming_message, send_audio, send_text
from whatsapp_server.security import limiter, verify_webhook_signature

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Same logger uvicorn uses, so these lines look like the rest of the server output.
logger = logging.getLogger("uvicorn.error")

_EXTENSION_FROM_MIMETYPE = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "text/plain": ".txt",
}

_APOLOGY = "Sorry — something went wrong on my side, so I couldn't answer that. Please try again in a moment."
_NO_REPLY = "I couldn't come up with a reply to that — could you rephrase it?"
_VOICE_FAILED = "Received a voice note but couldn't transcribe it."
_MEDIA_PROBLEMS = {
    "too_large": "That file is too large for me to download here.",
    "download_failed": "WhatsApp wouldn't let me download that — could you send it again?",
    "invalid_media": "That attachment arrived damaged — could you send it again?",
}


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

_locks_guard = threading.Lock()
_sender_locks: dict[str, threading.Lock] = {}


def _lock_for(sender: str) -> threading.Lock:
    with _locks_guard:
        return _sender_locks.setdefault(sender, threading.Lock())


def _log_error(what: str, exc: BaseException) -> None:
    """One readable line per failure; the full traceback only when LOG_LEVEL=DEBUG."""
    detail = str(exc) if isinstance(exc, BridgeError) else f"{type(exc).__name__}: {exc}"
    if settings.log_level.upper() == "DEBUG":
        logger.error("%s: %s", what, detail, exc_info=exc)
    else:
        logger.error("%s: %s", what, detail)


def _try_send_text(sender: str, text: str) -> None:
    """Best-effort message to the sender that never raises (used for apologies and status notes)."""
    try:
        send_text(sender, text)
    except Exception as exc:  # noqa: BLE001 — see module docstring
        _log_error(f"Could not message {sender}", exc)


def _deliver_reply(sender: str, reply: str, as_voice: bool) -> None:
    """Sends `reply` as a voice note if asked to (falling back to text), otherwise as text."""
    if as_voice:
        try:
            audio_bytes = synthesize_speech(reply, as_mp3=True)
            send_audio(sender, audio_bytes, mimetype="audio/mpeg")
            return
        except Exception as exc:  # noqa: BLE001 — ElevenLabs 429 / quota / bridge hiccup: don't go silent
            _log_error("Voice reply failed, falling back to text", exc)
    send_text(sender, reply)


# ---------------------------------------------------------------------------
# background tasks — none of these may raise
# ---------------------------------------------------------------------------


def _handle_smart_conversation(sender: str, text: str, is_voice: bool) -> None:
    """Generates a reply and sends as Audio if input was Audio, otherwise Text."""
    try:
        with _lock_for(sender):
            reply = ask_jarvis(agent, text, thread_id=f"whatsapp-{sender}") or _NO_REPLY
            _deliver_reply(sender, reply, as_voice=is_voice)
    except BridgeError as exc:
        # The reply exists but WhatsApp wouldn't take it. The same channel is broken, so there
        # is nobody to apologise to — log why (the message says what to do) and move on.
        _log_error(f"Could not deliver Jarvis's reply to {sender}", exc)
    except Exception as exc:  # noqa: BLE001 — LLM outage, quota, tool crash ...
        _log_error(f"Jarvis could not answer {sender}", exc)
        _try_send_text(sender, _APOLOGY)


def _handle_voice_note(sender: str, message: dict) -> None:
    """Transcribe the voice note, then answer it like any other message (as a voice note)."""
    audio = message.get("media_bytes")
    if not audio:
        _try_send_text(sender, _MEDIA_PROBLEMS.get(message.get("media_error"), _MEDIA_PROBLEMS["download_failed"]))
        return
    try:
        transcript = transcribe(audio)
    except Exception as exc:  # noqa: BLE001 — Deepgram error, bad audio, silence ...
        _log_error(f"Could not transcribe a voice note from {sender}", exc)
        transcript = ""
    if not transcript.strip():
        _try_send_text(sender, _VOICE_FAILED)
        return
    _handle_smart_conversation(sender, transcript, True)


def _safe_filename(name: str, mimetype: str) -> str:
    """The sender controls the filename: keep only its basename and harmless characters."""
    base = os.path.basename((name or "").replace("\\", "/"))
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip(" .") or "attachment"
    if not os.path.splitext(base)[1]:
        base += _EXTENSION_FROM_MIMETYPE.get(mimetype or "", "")
    return base[-100:]


def _handle_document_or_image(sender: str, message: dict) -> None:
    """Runs as a background task: ingest the already-attached media for
    RAG, confirm back. No download call needed — message["media_bytes"]
    is already decoded by bridge_client.extract_incoming_message."""
    media = message.get("media_bytes")
    if not media:
        _try_send_text(sender, _MEDIA_PROBLEMS.get(message.get("media_error"), _MEDIA_PROBLEMS["download_failed"]))
        return

    name = _safe_filename(message.get("filename", ""), message.get("mimetype", ""))
    # A private temp folder (works on Windows too — the old hard-coded "/tmp/" does not),
    # with the real file name inside, so RAG results are labelled "report.pdf" and not a random id.
    tmp_dir = tempfile.mkdtemp(prefix="jarvis_whatsapp_")
    try:
        path = os.path.join(tmp_dir, name)
        with open(path, "wb") as f:
            f.write(media)
        count = ingest_file(path, source="whatsapp")
        reply = (
            f"Got it — ingested {name} ({count} chunk(s)), now searchable."
            if count
            else f"Received {name} but couldn't extract any text from it."
        )
    except ValueError as exc:  # ingest_file's own "unsupported type / can't read" messages are user-facing
        reply = str(exc)
    except Exception as exc:  # noqa: BLE001 — OCR not installed, embedding API down, corrupt file ...
        _log_error(f"Could not ingest {name} from {sender}", exc)
        reply = f"Sorry, I couldn't process {name}. Please try again later."
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    _try_send_text(sender, reply)


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------


@app.post("/webhook")
@limiter.limit("30/minute")
async def webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    body: bytes = Depends(verify_webhook_signature),
):
    try:
        message = extract_incoming_message(json.loads(body))
    except ValueError as exc:  # includes json.JSONDecodeError
        logger.warning("Rejected a malformed webhook payload: %s", exc)
        raise HTTPException(status_code=400, detail="Malformed webhook payload")

    if message["from_me"]:
        return {"status": "ignored"}

    sender = message["sender"]

    # Handle Documents and Images
    if message["type"] in ("document", "image"):
        background_tasks.add_task(_handle_document_or_image, sender, message)
    # Smart Reply for Audio: Voice note from user -> transcribe -> Jarvis replies (as voice if possible)
    elif message["type"] == "audio":
        background_tasks.add_task(_handle_voice_note, sender, message)
    # Smart Reply for Text: Text message from user -> Jarvis replies (as text)
    elif message["text"].strip():
        background_tasks.add_task(_handle_smart_conversation, sender, message["text"], False)
    else:
        return {"status": "ignored"}  # nothing to answer — an empty prompt only makes the LLM API error

    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok"}
