"""transcribe(audio_bytes) -> str — Deepgram Nova-3, Urdu + English.

Uses Deepgram's batch transcribe_file call for simplicity and reliability.
A streaming version (dg.listen.v1.connect) is the lower-latency upgrade
path once this is working end to end — see the Tech Stack Guide.
"""

from deepgram import DeepgramClient

from config import settings

_client: DeepgramClient | None = None


def _get_client() -> DeepgramClient:
    global _client
    if _client is None:
        settings.require("deepgram_api_key")
        _client = DeepgramClient(api_key=settings.deepgram_api_key)
    return _client


def transcribe(audio_bytes: bytes) -> str:
    """audio_bytes: raw audio (wav/mp3/etc.) captured from the mic.

    `language="multi"` enables Nova-3's real-time code-switching, so a
    single clip mixing Urdu and English transcribes correctly without
    picking one language ahead of time.
    """
    response = _get_client().listen.v1.media.transcribe_file(
        request=audio_bytes,
        model="nova-3",
        language="multi",
        smart_format=True,
        punctuate=True,
    )
    return response.results.channels[0].alternatives[0].transcript
