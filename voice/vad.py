"""Voice-activity detection — webrtcvad, no account or model download needed.

Used during the ACTIVE conversation state to segment individual
utterances (separate from voice/wake_word.py, which listens for
"jarvis" while IDLE). webrtcvad is a thin wrapper around Google's WebRTC
VAD, a pure C extension — no ML model, nothing to download at all.

Note: webrtcvad is lightly maintained and still imports the now-
deprecated pkg_resources. It works (confirmed), just pin
`setuptools<81` alongside it if that becomes a hard error later.
"""

import numpy as np
import webrtcvad

SAMPLE_RATE = 16000        # webrtcvad only accepts 8000/16000/32000/48000
FRAME_DURATION_MS = 30     # webrtcvad only accepts 10/20/30
FRAME_LENGTH = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # 480 samples
VAD_AGGRESSIVENESS = 2     # 0 (least aggressive) to 3 (most aggressive)


class VoiceActivityDetector:
    def __init__(self):
        self._vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)

    @property
    def frame_length(self) -> int:
        return FRAME_LENGTH

    @property
    def sample_rate(self) -> int:
        return SAMPLE_RATE

    def is_speech(self, pcm_frame) -> bool:
        """pcm_frame: exactly FRAME_LENGTH 16-bit int samples."""
        frame_bytes = np.array(pcm_frame, dtype=np.int16).tobytes()
        return self._vad.is_speech(frame_bytes, SAMPLE_RATE)

    def close(self) -> None:
        pass  # nothing to release
