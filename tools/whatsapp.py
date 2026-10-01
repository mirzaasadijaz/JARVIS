"""@tool send_whatsapp_message, send_whatsapp_voice_note.

For the agent to proactively send WhatsApp messages when asked (e.g. via
voice: "tell Ahmed I'm running late"). Separate from
whatsapp_server/webhook.py, which handles *incoming* messages — this
file is what the agent calls, that file is what calls the agent.
"""

from langchain_core.tools import tool

from voice.tts import synthesize_speech
from whatsapp_server.bridge_client import send_audio, send_text


@tool
def send_whatsapp_message(to: str, message: str) -> str:
    """Send a WhatsApp text message to a contact.

    Args:
        to: Phone number in international format, no leading '+' (e.g. "923001234567")
        message: The text to send
    """
    send_text(to, message)
    return f"Sent to {to}: {message}"


@tool
def send_whatsapp_voice_note(to: str, message: str) -> str:
    """Send a WhatsApp voice note (synthesized speech) instead of text.

    Args:
        to: Phone number in international format, no leading '+'
        message: The text to speak and send as a voice note
    """
    audio_bytes = synthesize_speech(message, as_mp3=True)
    send_audio(to, audio_bytes, mimetype="audio/mpeg")
    return f"Sent voice note to {to}"
