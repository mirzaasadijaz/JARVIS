"""@tool send_whatsapp_message, send_whatsapp_voice_note.

For the agent to proactively send WhatsApp messages when asked (e.g. via
voice: "tell Ahmed I'm running late"). Separate from
whatsapp_server/webhook.py, which handles *incoming* messages — this
file is what the agent calls, that file is what calls the agent.
"""

from langchain_core.tools import tool

from voice.tts import synthesize_speech
from whatsapp_server.bridge_client import BridgeError, send_audio, send_text


@tool
def send_whatsapp_message(to: str, message: str) -> str:
    """Send a WhatsApp text message to a contact.

    Args:
        to: Phone number in international format, no leading '+' (e.g. "923001234567")
        message: The text to send
    """
    try:
        send_text(to, message)
    except BridgeError as exc:
        # Returned, not raised: the agent can then tell the user *why* (number not on
        # WhatsApp, bridge not running ...) instead of the tool being blindly retried.
        return f"Could not send the WhatsApp message: {exc}"
    return f"Sent to {to}: {message}"


@tool
def send_whatsapp_voice_note(to: str, message: str) -> str:
    """Send a WhatsApp voice note (synthesized speech) instead of text.

    Args:
        to: Phone number in international format, no leading '+'
        message: The text to speak and send as a voice note
    """
    try:
        audio_bytes = synthesize_speech(message, as_mp3=True)
    except Exception as exc:  # noqa: BLE001 — ElevenLabs quota / key / network
        return f"Could not create the voice note ({type(exc).__name__}: {exc}). Offer to send it as a text message instead."
    try:
        send_audio(to, audio_bytes, mimetype="audio/mpeg")
    except BridgeError as exc:
        return f"Could not send the voice note: {exc}"
    return f"Sent voice note to {to}"
