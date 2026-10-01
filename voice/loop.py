"""Wires the whole voice pipeline together as a state machine:

  IDLE  -- "jarvis" heard --> PIN PROMPT
  PIN PROMPT -- correct --> ACTIVE
  PIN PROMPT -- wrong/closed --> IDLE  (try "jarvis" again)
  ACTIVE -- normal speech --> agent -> spoken reply -> stays ACTIVE
  ACTIVE -- "bye jarvis" heard in transcript --> program exits entirely

Two different mic configurations are used because the two engines expect
different chunk sizes: openWakeWord wants 1280-sample chunks (80ms),
webrtcvad wants 480-sample chunks (30ms) — see wake_word.py / vad.py.
Rather than force one chunk size on both, the input stream is closed and
reopened at the right size when switching between IDLE and ACTIVE.

Honest caveat: like the original version of this file, this can't be
verified without real hardware (mic, speakers, and now also a display
for the PIN popup) — everything here is written to each library's
actually-checked API, but expect to tune WAKE_THRESHOLD (wake_word.py)
and SILENCE_FRAMES_TO_END_UTTERANCE below against your own setup.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sounddevice as sd

from core.agent import agent
from core.pin_lock import prompt_for_pin
from voice.audio_utils import frames_to_wav_bytes, play_pcm
from voice.stt import transcribe
from voice.tts import SAMPLE_RATE as TTS_SAMPLE_RATE
from voice.tts import synthesize_speech
from voice.vad import VoiceActivityDetector
from voice.wake_word import CHUNK_SIZE as WAKE_CHUNK_SIZE
from voice.wake_word import SAMPLE_RATE as WAKE_SAMPLE_RATE
from voice.wake_word import detect_wake_word

SILENCE_FRAMES_TO_END_UTTERANCE = 20  # tune against your mic/room
EXIT_PHRASE = "bye jarvis"
THREAD_ID = "voice-loop"


def _wait_for_wake_word() -> None:
    """Blocks until "jarvis" is heard. Cheap and local — no STT or LLM
    calls happen out here, so idling costs nothing but CPU."""
    print("Jarvis is idle — say 'jarvis' to start.")
    stream = sd.InputStream(
        samplerate=WAKE_SAMPLE_RATE, channels=1, dtype="int16", blocksize=WAKE_CHUNK_SIZE
    )
    stream.start()
    try:
        while True:
            frame, _ = stream.read(WAKE_CHUNK_SIZE)
            if detect_wake_word(frame.flatten().tolist()):
                return
    finally:
        stream.stop()
        stream.close()


def _handle_utterance(frames, mic_sample_rate: int) -> bool:
    """Returns False if this utterance was "bye jarvis" (caller should
    exit), True otherwise."""
    text = transcribe(frames_to_wav_bytes(frames, mic_sample_rate))
    if not text.strip():
        return True

    print(f"You: {text}")
    if EXIT_PHRASE in text.lower():
        play_pcm(synthesize_speech("Goodbye."), TTS_SAMPLE_RATE)
        return False

    result = agent.invoke(
        {"messages": [{"role": "user", "content": text}]},
        config={"configurable": {"thread_id": THREAD_ID}},
    )
    reply = result["messages"][-1].content
    print(f"Jarvis: {reply}")
    play_pcm(synthesize_speech(reply), TTS_SAMPLE_RATE)
    return True


def _run_active_session() -> bool:
    """Runs the normal listen -> transcribe -> agent -> speak loop until
    "bye jarvis" is heard. Returns False (signals the whole program
    should exit) when that happens."""
    vad = VoiceActivityDetector()
    print("Unlocked. Jarvis is listening.")
    play_pcm(synthesize_speech("I'm listening."), TTS_SAMPLE_RATE)

    utterance_frames: list[int] = []
    silence_run = 0
    in_utterance = False

    stream = sd.InputStream(
        samplerate=vad.sample_rate, channels=1, dtype="int16", blocksize=vad.frame_length
    )
    stream.start()

    try:
        while True:
            frame, _ = stream.read(vad.frame_length)
            frame = frame.flatten().tolist()

            if vad.is_speech(frame):
                in_utterance = True
                silence_run = 0
                utterance_frames.extend(frame)
            elif in_utterance:
                silence_run += 1
                utterance_frames.extend(frame)
                if silence_run >= SILENCE_FRAMES_TO_END_UTTERANCE:
                    keep_going = _handle_utterance(utterance_frames, vad.sample_rate)
                    if not keep_going:
                        return False
                    utterance_frames = []
                    in_utterance = False
                    silence_run = 0
    finally:
        stream.stop()
        stream.close()
        vad.close()


def run() -> None:
    while True:
        _wait_for_wake_word()

        if not prompt_for_pin():
            print("Incorrect PIN.")
            continue

        keep_running = _run_active_session()
        if not keep_running:
            print("Jarvis is shutting down.")
            return


if __name__ == "__main__":
    run()
