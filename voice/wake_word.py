"""Wake-word detection — openWakeWord, no account or paid API needed.

Uses the "hey_jarvis" pretrained model. Loads all of openWakeWord's
bundled models via Model()'s defaults and filters by key name in the
result, rather than reaching into openwakeword.models[...] for a
specific file path — that internal registry's shape changed between
openwakeword versions (confirmed: 0.4.0 has it, a newer resolved
version doesn't), while Model() and .predict()'s dict return are the
stable public surface. Costs a bit of unused inference on the other
bundled models (alexa, timers, weather), which is cheap enough not to
matter here.
"""

import numpy as np
from openwakeword.model import Model

SAMPLE_RATE = 16000
CHUNK_SIZE = 1280  # openWakeWord's expected chunk size (80ms @ 16kHz)
WAKE_THRESHOLD = 0.5

_model = None


def _get_model() -> Model:
    global _model
    if _model is None:
        _model = Model()  # loads all bundled pretrained models
    return _model


def detect_wake_word(pcm_chunk) -> bool:
    """pcm_chunk: exactly CHUNK_SIZE 16-bit int samples."""
    scores = _get_model().predict(np.array(pcm_chunk, dtype=np.int16))
    return any("jarvis" in key.lower() and score >= WAKE_THRESHOLD for key, score in scores.items())
