"""synthesize_speech(text) -> bytes — ElevenLabs Flash v2.5, low latency.

Returns raw audio bytes (mp3) ready to play or save. Swap voice_id for
Azure's ur-PK-AsadNeural (see the Tech Stack Guide) if you'd rather use
a dedicated Urdu voice for Urdu-heavy replies.
"""

from elevenlabs.client import ElevenLabs

from config import settings

DEFAULT_VOICE_ID = "lJh4ZtsSfESh4WpLX8Gc"  # ElevenLabs' default "Rachel" voice — swap for your pick

_client: ElevenLabs | None = None


def _get_client() -> ElevenLabs:
    global _client
    if _client is None:
        settings.require("elevenlabs_api_key")
        _client = ElevenLabs(api_key=settings.elevenlabs_api_key)
    return _client


SAMPLE_RATE = 24000  # matches the default pcm output below


def synthesize_speech(text: str, voice_id: str = DEFAULT_VOICE_ID, as_mp3: bool = False) -> bytes:
    """Returns synthesized audio for `text`.

    as_mp3=False (default): raw 16-bit PCM at SAMPLE_RATE, no container —
    correct for direct local playback via voice/audio_utils.play_pcm,
    where we control both the encode and decode side.

    as_mp3=True: a real MP3 container — use this for anything that
    leaves the process, like tools/whatsapp.py's voice notes. WhatsApp
    needs an actual audio format, not headerless PCM.
    """
    output_format = "mp3_44100_128" if as_mp3 else "pcm_24000"
    audio_chunks = _get_client().text_to_speech.convert(
        voice_id,
        text=text,
        model_id="eleven_flash_v2_5",
        output_format=output_format,
    )
    return b"".join(audio_chunks)
