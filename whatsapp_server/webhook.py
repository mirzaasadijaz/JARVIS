"""FastAPI app + /webhook route — receives events from the whatsapp-web.js
bridge (whatsapp_bridge/server.js), not Evolution API.

Document/image attachments, from anyone: ingested into the RAG
store (tools/documents.py) so their contents become searchable.

Smart Replies: 
- If a user sends a text, Jarvis replies with text.
- If a user sends a voice note, Jarvis replies with a voice note. 
- If ElevenLabs API limit is reached (429), Jarvis automatically falls back to text.
"""

import json
import os
import uuid

from fastapi import BackgroundTasks, Depends, FastAPI, Request
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from config import settings
from core.agent import agent
from tools.documents import ingest_file
from voice.stt import transcribe
from voice.tts import synthesize_speech
from whatsapp_server.bridge_client import extract_incoming_message, send_text, send_audio
from whatsapp_server.security import limiter, verify_webhook_signature

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_EXTENSION_FROM_MIMETYPE = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "text/plain": ".txt",
}


def _handle_smart_conversation(sender: str, text: str, is_voice: bool) -> None:
    """Generates a reply and sends as Audio if input was Audio, otherwise Text."""
    # 1. Jarvis se reply generate karwayen
    result = agent.invoke(
        {"messages": [{"role": "user", "content": text}]},
        config={"configurable": {"thread_id": f"whatsapp-{sender}"}},
    )
    jarvis_reply_text = result["messages"][-1].content

    # 2. Smart Reply Fallback Logic
    if is_voice:
        try:
            # Agar user ne voice bheji hai, toh audio generate karke send_audio call karein
            audio_bytes = synthesize_speech(jarvis_reply_text, as_mp3=True)
            send_audio(sender, audio_bytes, mimetype="audio/mp3")
        except Exception as e:
            # Agar ElevenLabs 429 error de, toh crash hone ke bajaye simple text bhej dein
            print(f"ElevenLabs limit reached or error, falling back to text: {e}")
            send_text(sender, jarvis_reply_text)
    else:
        # Agar incoming message text tha, toh sirf text bhej dein
        send_text(sender, jarvis_reply_text)


def _handle_document_or_image(sender: str, message: dict) -> None:
    """Runs as a background task: ingest the already-attached media for
    RAG, confirm back. No download call needed — message["media_bytes"]
    is already decoded by bridge_client.extract_incoming_message."""
    ext = os.path.splitext(message["filename"])[1] or _EXTENSION_FROM_MIMETYPE.get(message["mimetype"], "")
    temp_path = f"/tmp/{uuid.uuid4()}{ext}"
    with open(temp_path, "wb") as f:
        f.write(message["media_bytes"])

    try:
        count = ingest_file(temp_path, source="whatsapp")
        reply = (
            f"Got it — ingested {message['filename']} ({count} chunk(s)), now searchable."
            if count
            else f"Received {message['filename']} but couldn't extract any text from it."
        )
    except ValueError as e:
        reply = str(e)
    finally:
        os.remove(temp_path)

    send_text(sender, reply)


@app.post("/webhook")
@limiter.limit("30/minute")
async def webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    body: bytes = Depends(verify_webhook_signature),
):
    payload = json.loads(body)
    message = extract_incoming_message(payload)
    
    if message["from_me"]:
        return {"status": "ignored"}

    sender = message["sender"]

    # Handle Documents and Images
    if message["type"] in ("document", "image"):
        background_tasks.add_task(_handle_document_or_image, sender, message)
        return {"status": "ok"}

    # Smart Reply for Audio: Voice note from user -> transcribe -> Jarvis replies (as voice if possible)
    if message["type"] == "audio":
        transcript = transcribe(message["media_bytes"])
        if transcript.strip():
            background_tasks.add_task(_handle_smart_conversation, sender, transcript, True)
        else:
            send_text(sender, "Received a voice note but couldn't transcribe it.")
        return {"status": "ok"}

    # Smart Reply for Text: Text message from user -> Jarvis replies (as text)
    text = message["text"]
    background_tasks.add_task(_handle_smart_conversation, sender, text, False)

    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok"}