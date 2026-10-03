"""The other files touched by the fix: agent WhatsApp tools, OCR, the voice loop, the terminal approver."""

import ast
import importlib.util
import sys
import types

import pytest
from langchain_core.messages import AIMessage

from conftest import ROOT, Stubs

LID = "22952607240241@lid"


# ---------------------------------------------------------------------------------------------
# tools/whatsapp.py — failures come back to the agent as readable text instead of raising
# ---------------------------------------------------------------------------------------------


@pytest.fixture
def wa_tools():
    from tools import whatsapp

    return whatsapp


def test_send_message_tool_success(wa_tools, bridge):
    out = wa_tools.send_whatsapp_message.invoke({"to": "923001234567", "message": "hi"})
    assert out == "Sent to 923001234567: hi" and bridge.texts() == ["hi"]


def test_send_message_tool_reports_unregistered_number_to_the_agent(wa_tools, bridge):
    bridge.fail_with(404, "923009999999 is not registered on WhatsApp.", code="not_on_whatsapp")
    out = wa_tools.send_whatsapp_message.invoke({"to": "923009999999", "message": "hi"})
    assert out.startswith("Could not send the WhatsApp message") and "not registered on WhatsApp" in out
    assert len(bridge.requests) == 1, "must not be retried blindly"


def test_send_message_tool_when_bridge_is_down(wa_tools, bridge):
    bridge.stop()
    assert "npm start" in wa_tools.send_whatsapp_message.invoke({"to": "923001234567", "message": "hi"})


def test_voice_note_tool_paths(wa_tools, bridge):
    assert wa_tools.send_whatsapp_voice_note.invoke({"to": "923001234567", "message": "hello"}) == "Sent voice note to 923001234567"
    assert bridge.audios()[0]["mimetype"] == "audio/mpeg"

    bridge.fail_with(502, "No LID", code="no_lid")
    assert wa_tools.send_whatsapp_voice_note.invoke({"to": "923001234567", "message": "x"}).startswith("Could not send the voice note")

    def broken(*a, **k):
        raise RuntimeError("ElevenLabs quota")

    Stubs.synthesize = staticmethod(broken)
    out = wa_tools.send_whatsapp_voice_note.invoke({"to": "923001234567", "message": "x"})
    assert out.startswith("Could not create the voice note") and "text message" in out


# ---------------------------------------------------------------------------------------------
# tools/memory.py — the copy-pasted duplicate block is gone
# ---------------------------------------------------------------------------------------------


def test_memory_tools_are_defined_once():
    tree = ast.parse((ROOT / "tools" / "memory.py").read_text(encoding="utf-8"))
    names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    assert names.count("save_note") == 1 and names.count("search_notes") == 1


# ---------------------------------------------------------------------------------------------
# tools/documents.py — OCR
# ---------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_documents():
    """Loads the REAL tools/documents.py (conftest stubs the importable one) with only the DB stack faked."""
    pytest.importorskip("pytesseract")
    pytest.importorskip("PIL")
    fakes = {
        "chromadb": types.ModuleType("chromadb"),
        "openpyxl": types.ModuleType("openpyxl"),
        "pypdf": types.SimpleNamespace(PdfReader=object),
        "docx": types.SimpleNamespace(Document=object),
        "core.embeddings": types.SimpleNamespace(VoyageEmbeddingFunction=object),
    }
    saved = {k: sys.modules.get(k) for k in fakes}
    sys.modules.update(fakes)
    try:
        spec = importlib.util.spec_from_file_location("real_documents", ROOT / "tools" / "documents.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _png_with_text(path, text="Hello Jarvis 12345"):
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (900, 160), "white")
    ImageDraw.Draw(img).text((20, 40), text, fill="black", font=ImageFont.load_default(size=64))
    img.save(path)


def test_ocr_reads_an_image_and_releases_the_file(real_documents, tmp_path):
    import shutil

    if not shutil.which("tesseract"):
        pytest.skip("tesseract binary not installed here")
    p = tmp_path / "scan.png"
    _png_with_text(p)
    assert "Hello" in real_documents._extract_text(str(p))
    p.unlink()  # on Windows this raised PermissionError while the image handle was still open


def test_missing_tesseract_becomes_a_clear_user_facing_message(real_documents, tmp_path, monkeypatch):
    import pytesseract

    p = tmp_path / "scan.png"
    _png_with_text(p)
    monkeypatch.setattr(pytesseract.pytesseract, "tesseract_cmd", str(tmp_path / "no-such-tesseract.exe"))  # = a Windows PC without it
    with pytest.raises(ValueError, match="Tesseract OCR program isn't installed"):
        real_documents._extract_text(str(p))


# ---------------------------------------------------------------------------------------------
# voice/loop.py — one bad turn must not end the session
# ---------------------------------------------------------------------------------------------


@pytest.fixture
def loop(monkeypatch):
    spoken, state = [], {"transcript": "what time is it"}
    fakes = {
        "sounddevice": types.ModuleType("sounddevice"),
        "core.pin_lock": types.SimpleNamespace(prompt_for_pin=lambda: True),
        "voice.audio_utils": types.SimpleNamespace(frames_to_wav_bytes=lambda f, r: b"wav", play_pcm=lambda audio, rate: spoken.append(audio)),
        "voice.vad": types.SimpleNamespace(VoiceActivityDetector=object),
        "voice.wake_word": types.SimpleNamespace(CHUNK_SIZE=1280, SAMPLE_RATE=16000, detect_wake_word=lambda f: False),
    }
    for k, v in fakes.items():
        monkeypatch.setitem(sys.modules, k, v)
    sys.modules.pop("voice.loop", None)
    Stubs.transcribe = staticmethod(lambda audio: state["transcript"])
    Stubs.synthesize = staticmethod(lambda text, *a, **k: text.encode())  # "audio" = the text, so we can see what was said
    import voice.loop as mod

    monkeypatch.setattr(mod, "transcribe", lambda audio: Stubs.transcribe(audio))
    yield mod, spoken, state
    sys.modules.pop("voice.loop", None)


class OneShotAgent:
    def __init__(self, reply=None, error=None):
        self.reply, self.error = reply, error

    def invoke(self, payload, config=None):
        if self.error:
            raise self.error
        return {"messages": [AIMessage(content=self.reply)]}

    def get_state(self, config):
        raise RuntimeError("n/a")


def test_voice_turn_speaks_the_reply(loop):
    mod, spoken, _ = loop
    Stubs.agent = OneShotAgent("It is noon.")
    assert mod._handle_utterance([0] * 10, 16000) is True
    assert spoken == [b"It is noon."]


def test_voice_turn_survives_an_llm_outage(loop):
    mod, spoken, _ = loop
    Stubs.agent = OneShotAgent(error=RuntimeError("503 overloaded"))
    assert mod._handle_utterance([0] * 10, 16000) is True  # used to propagate and end the whole session
    assert spoken == [b"Sorry, something went wrong. Please try again."]


def test_voice_turn_survives_tts_and_stt_failures(loop):
    mod, spoken, state = loop
    Stubs.agent = OneShotAgent("fine")

    def broken(*a, **k):
        raise RuntimeError("tts down")

    Stubs.synthesize = staticmethod(broken)
    assert mod._handle_utterance([0] * 10, 16000) is True and spoken == []

    def broken_stt(audio):
        raise RuntimeError("stt down")

    Stubs.transcribe = staticmethod(broken_stt)
    assert mod._handle_utterance([0] * 10, 16000) is True


def test_voice_exit_phrase_and_silence(loop):
    mod, spoken, state = loop
    Stubs.agent = OneShotAgent("never used")
    state["transcript"] = "ok bye jarvis"
    assert mod._handle_utterance([0], 16000) is False and spoken == [b"Goodbye."]
    state["transcript"] = "  "
    assert mod._handle_utterance([0], 16000) is True


def test_voice_turn_with_empty_reply_and_list_reply(loop):
    mod, spoken, _ = loop
    Stubs.agent = OneShotAgent("")
    mod._handle_utterance([0], 16000)
    assert spoken == [b"I don't have a reply for that."]
    Stubs.agent = OneShotAgent([{"type": "text", "text": "From blocks"}])
    mod._handle_utterance([0], 16000)
    assert spoken[-1] == b"From blocks"


# ---------------------------------------------------------------------------------------------
# core/agent.py — terminal approver (the module itself needs every tool/API key to import)
# ---------------------------------------------------------------------------------------------


def test_terminal_approver(monkeypatch):
    src = (ROOT / "core" / "agent.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name == "_ask_in_terminal")
    ns = {}
    exec(compile(ast.Module([fn], []), "agent.py", "exec"), ns)
    answers = iter(["y", "n"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    decisions = ns["_ask_in_terminal"]([{"name": "send_email", "args": {}}, {"name": "write_file", "args": {}}])
    assert decisions[0] == {"type": "approve"} and decisions[1]["type"] == "reject"
