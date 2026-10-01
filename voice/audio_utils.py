"""Small shared helpers for converting between raw PCM and WAV bytes."""

import io
import wave

import numpy as np


def frames_to_wav_bytes(frames: list[int], sample_rate: int) -> bytes:
    """Wraps raw int16 PCM samples in a minimal in-memory WAV container.
    Used before sending audio to Deepgram, which needs a self-describing
    format since it's an external API."""
    pcm = np.array(frames, dtype=np.int16).tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def play_pcm(audio_bytes: bytes, sample_rate: int) -> None:
    """Plays raw int16 PCM directly through the default output device."""
    import sounddevice as sd

    data = np.frombuffer(audio_bytes, dtype=np.int16)
    sd.play(data, samplerate=sample_rate)
    sd.wait()
