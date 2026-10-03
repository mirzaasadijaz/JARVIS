"""The WhatsApp path end to end: Node bridge (faked) -> /webhook -> agent -> reply back to the bridge.

The headline test is `test_the_reported_bridge_error_no_longer_escapes`: the bridge answers
exactly as in the bug report (HTTP 500 {"error": "No LID for user ..."}) and the server must
neither raise out of the background task ("Exception in ASGI application") nor misbehave.
"""

import threading
import time

import pytest
import requests
from langchain_core.messages import AIMessage, HumanMessage

import whatsapp_server.webhook as webhook_module
from conftest import Stubs, signed_post
from whatsapp_server.bridge_client import BridgeError, extract_incoming_message, send_audio, send_text

LID = "22952607240241@lid"
NO_LID = "No LID for user\ns (https://static.whatsapp.net/rsrc.php/v4/y0/r/1ypFDhyoVzg.js:85:180)"


class FakeAgent:
    """A minimal agent: replies with fixed text, or raises."""

    def __init__(self, reply="Hi there!", error=None, delay=0.0):
        self.reply, self.error, self.delay = reply, error, delay
        self.calls = []
        self.active = 0
        self.max_active = 0

    def invoke(self, payload, config=None):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            self.calls.append((payload, config))
            time.sleep(self.delay)
            if self.error:
                raise self.error
            return {"messages": [HumanMessage("x"), AIMessage(content=self.reply)]}
        finally:
            self.active -= 1

    def get_state(self, config):
        raise RuntimeError("no checkpointer in this fake")


def text_msg(text="hello", sender=LID):
    return {"sender": sender, "from_me": False, "type": "text", "text": text}


# ---------------------------------------------------------------------------------------------
# the reported error
# ---------------------------------------------------------------------------------------------


def test_the_reported_bridge_error_no_longer_escapes(webhook_client, bridge, capsys):
    Stubs.agent = FakeAgent("Here is my answer")
    bridge.fail_with(500, NO_LID)

    r = signed_post(webhook_client, text_msg())  # would raise HTTPError from the task before the fix

    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert bridge.texts() == ["Here is my answer"]  # it did try to deliver
    log = capsys.readouterr()
    assert "Traceback" not in log.out + log.err


def test_failure_message_is_readable_not_a_stack_trace(webhook_client, bridge, caplog):
    Stubs.agent = FakeAgent()
    bridge.fail_with(404, "923009999999 is not registered on WhatsApp.", code="not_on_whatsapp")
    with caplog.at_level("ERROR", logger="uvicorn.error"):
        signed_post(webhook_client, text_msg())
    errors = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(errors) == 1 and errors[0].exc_info is None
    assert "not registered on WhatsApp" in errors[0].getMessage()


def test_bridge_not_running_is_handled(webhook_client, bridge):
    Stubs.agent = FakeAgent()
    bridge.stop()  # connection refused
    assert signed_post(webhook_client, text_msg()).status_code == 200


# ---------------------------------------------------------------------------------------------
# normal behaviour
# ---------------------------------------------------------------------------------------------


def test_text_in_text_out(webhook_client, bridge):
    agent = Stubs.agent = FakeAgent("Hello Asad")
    assert signed_post(webhook_client, text_msg("hi jarvis")).status_code == 200
    assert bridge.requests == [("/send-text", {"to": LID, "text": "Hello Asad"})]
    payload, config = agent.calls[0]
    assert payload["messages"][0]["content"] == "hi jarvis"
    assert config["configurable"]["thread_id"] == f"whatsapp-{LID}"  # same threads as before: history is kept


def test_both_id_formats_are_replied_to_as_is(webhook_client, bridge):
    Stubs.agent = FakeAgent("ok")
    signed_post(webhook_client, text_msg(sender="923001234567@c.us"))
    assert bridge.requests[0][1]["to"] == "923001234567@c.us"


def test_llm_failure_apologises_instead_of_going_silent(webhook_client, bridge):
    Stubs.agent = FakeAgent(error=RuntimeError("429 quota exceeded"))
    assert signed_post(webhook_client, text_msg()).status_code == 200
    assert len(bridge.texts()) == 1 and "went wrong" in bridge.texts()[0]
    assert "429" not in bridge.texts()[0], "internal error details must not be sent to the sender"


def test_llm_failure_and_dead_bridge_together(webhook_client, bridge):
    Stubs.agent = FakeAgent(error=RuntimeError("boom"))
    bridge.stop()
    assert signed_post(webhook_client, text_msg()).status_code == 200


def test_empty_prompts_never_reach_the_llm(webhook_client, bridge):
    agent = Stubs.agent = FakeAgent()
    for t in ("", "   ", "\n"):
        assert signed_post(webhook_client, text_msg(t)).json() == {"status": "ignored"}
    assert agent.calls == [] and bridge.requests == []


def test_empty_agent_reply_gets_a_fallback_not_an_empty_whatsapp_message(webhook_client, bridge):
    Stubs.agent = FakeAgent("")
    signed_post(webhook_client, text_msg())
    assert bridge.texts() and bridge.texts()[0].strip()


def test_sensitive_action_requested_over_whatsapp(webhook_client, bridge, make_agent):
    sensitive = AIMessage(content="", tool_calls=[{"name": "send_whatsapp_message", "args": {"to": "92300", "message": "hi"}, "id": "c1"}])
    agent, model = make_agent([sensitive, AIMessage(content="That needs your OK on the PC."), AIMessage(content="Still here!")])
    Stubs.agent = agent

    signed_post(webhook_client, text_msg("message Ahmed hi"))
    signed_post(webhook_client, text_msg("you there?"))

    assert bridge.texts() == ["That needs your OK on the PC.", "Still here!"]  # both answered; neither empty nor an error
    assert all(m for m in bridge.texts())


def test_from_me_is_ignored(webhook_client, bridge):
    agent = Stubs.agent = FakeAgent()
    p = text_msg()
    p["from_me"] = True
    assert signed_post(webhook_client, p).json() == {"status": "ignored"}
    assert agent.calls == []


def test_messages_from_one_sender_never_overlap(bridge):
    agent = Stubs.agent = FakeAgent("ok", delay=0.15)
    threads = [threading.Thread(target=webhook_module._handle_smart_conversation, args=(LID, f"m{i}", False)) for i in range(3)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(agent.calls) == 3 and agent.max_active == 1


def test_different_senders_run_in_parallel(bridge):
    agent = Stubs.agent = FakeAgent("ok", delay=0.2)
    threads = [threading.Thread(target=webhook_module._handle_smart_conversation, args=(f"{i}@lid", "m", False)) for i in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert agent.max_active == 2


# ---------------------------------------------------------------------------------------------
# voice notes
# ---------------------------------------------------------------------------------------------


def voice_msg(**over):
    import base64

    p = {"sender": LID, "from_me": False, "type": "audio", "text": "", "media_base64": base64.b64encode(b"opus").decode(), "mimetype": "audio/ogg; codecs=opus", "filename": "ptt.ogg"}
    p.update(over)
    return p


def test_voice_note_gets_a_voice_reply(webhook_client, bridge):
    heard = []
    Stubs.transcribe = staticmethod(lambda audio: heard.append(audio) or "what time is it")
    spoken = []
    Stubs.synthesize = staticmethod(lambda text, *a, **k: spoken.append(text) or b"mp3")
    agent = Stubs.agent = FakeAgent("It is noon.")

    assert signed_post(webhook_client, voice_msg()).status_code == 200

    assert heard == [b"opus"] and spoken == ["It is noon."]
    assert agent.calls[0][0]["messages"][0]["content"] == "what time is it"
    (audio,) = bridge.audios()
    assert audio["to"] == LID and audio["mimetype"] == "audio/mpeg"  # not the non-standard "audio/mp3"


def test_voice_reply_falls_back_to_text_when_tts_fails(webhook_client, bridge):
    Stubs.transcribe = staticmethod(lambda audio: "hello")

    def broken_tts(*a, **k):
        raise RuntimeError("ElevenLabs 429")

    Stubs.synthesize = staticmethod(broken_tts)
    Stubs.agent = FakeAgent("Text instead")
    assert signed_post(webhook_client, voice_msg()).status_code == 200
    assert bridge.texts() == ["Text instead"] and bridge.audios() == []


def test_transcription_failure_is_reported_to_the_sender(webhook_client, bridge):
    def broken_stt(audio):
        raise RuntimeError("deepgram 401")

    Stubs.transcribe = staticmethod(broken_stt)
    Stubs.agent = FakeAgent()
    assert signed_post(webhook_client, voice_msg()).status_code == 200  # used to be a 500
    assert bridge.texts() == ["Received a voice note but couldn't transcribe it."]


def test_silent_voice_note(webhook_client, bridge):
    Stubs.transcribe = staticmethod(lambda audio: "   ")
    agent = Stubs.agent = FakeAgent()
    signed_post(webhook_client, voice_msg())
    assert agent.calls == [] and "couldn't transcribe" in bridge.texts()[0]


def test_voice_note_that_could_not_be_downloaded(webhook_client, bridge):
    agent = Stubs.agent = FakeAgent()
    p = {"sender": LID, "from_me": False, "type": "audio", "text": "", "media_error": "download_failed"}  # used to be a KeyError -> 500
    assert signed_post(webhook_client, p).status_code == 200
    assert "send it again" in bridge.texts()[0] and agent.calls == []


# ---------------------------------------------------------------------------------------------
# documents / images
# ---------------------------------------------------------------------------------------------


def doc_msg(filename="report.pdf", mimetype="application/pdf", data=b"%PDF-fake", **over):
    import base64

    p = {"sender": LID, "from_me": False, "type": "document", "text": "", "media_base64": base64.b64encode(data).decode(), "mimetype": mimetype, "filename": filename}
    p.update(over)
    return p


def test_document_is_ingested_from_a_real_temp_file_and_cleaned_up(webhook_client, bridge):
    import os

    seen = {}

    def ingest(path, source="computer"):
        seen.update(path=path, source=source, data=open(path, "rb").read(), existed=os.path.exists(path))
        return 3

    Stubs.ingest = staticmethod(ingest)
    signed_post(webhook_client, doc_msg())

    assert seen["data"] == b"%PDF-fake" and seen["source"] == "whatsapp"
    assert os.path.basename(seen["path"]) == "report.pdf"  # real name kept -> RAG results are labelled usefully
    assert not os.path.exists(seen["path"]) and not os.path.exists(os.path.dirname(seen["path"]))
    assert "ingested report.pdf (3 chunk(s))" in bridge.texts()[0]


def test_image_without_extension_gets_one_from_the_mimetype(webhook_client, bridge):
    seen = {}
    Stubs.ingest = staticmethod(lambda path, source="computer": seen.update(name=__import__("os").path.basename(path)) or 1)
    signed_post(webhook_client, doc_msg("whatsapp_image", "image/jpeg", type="image"))
    assert seen["name"] == "whatsapp_image.jpg"


@pytest.mark.parametrize("evil", ["../../etc/passwd", "..\\..\\Windows\\evil.pdf", "C:\\x\\y.docx", "a/b/c.txt", "", "   "])
def test_hostile_filenames_stay_inside_the_temp_folder(webhook_client, bridge, evil):
    import os
    import tempfile

    seen = {}
    Stubs.ingest = staticmethod(lambda path, source="computer": seen.update(path=path) or 1)
    signed_post(webhook_client, doc_msg(evil))
    parent = os.path.dirname(os.path.realpath(seen["path"]))
    assert parent.startswith(os.path.realpath(tempfile.gettempdir())) and os.path.basename(parent).startswith("jarvis_whatsapp_")


def test_unsupported_file_type_message_is_passed_on(webhook_client, bridge):
    def ingest(path, source="computer"):
        raise ValueError("Unsupported file type: .exe (supported: ['.pdf'])")

    Stubs.ingest = staticmethod(ingest)
    signed_post(webhook_client, doc_msg("x.exe"))
    assert bridge.texts() == ["Unsupported file type: .exe (supported: ['.pdf'])"]


def test_unexpected_ingest_failure_is_reported_not_raised(webhook_client, bridge):
    def ingest(path, source="computer"):
        raise OSError("voyage embedding API is down")

    Stubs.ingest = staticmethod(ingest)
    assert signed_post(webhook_client, doc_msg()).status_code == 200
    assert "couldn't process report.pdf" in bridge.texts()[0]
    assert "voyage" not in bridge.texts()[0]


def test_attachment_that_could_not_be_downloaded(webhook_client, bridge):
    p = {"sender": LID, "from_me": False, "type": "document", "text": "", "media_error": "too_large"}
    signed_post(webhook_client, p)
    assert "too large" in bridge.texts()[0]


# ---------------------------------------------------------------------------------------------
# request validation
# ---------------------------------------------------------------------------------------------


def test_bad_signature_is_401(webhook_client, bridge):
    assert signed_post(webhook_client, text_msg(), secret="wrong").status_code == 401


def test_non_ascii_signature_header_is_401_not_a_server_error(webhook_client):
    r = webhook_client.post("/webhook", content=b"{}", headers={"x-webhook-signature": "sha256=é".encode("latin-1")})
    assert r.status_code == 401


@pytest.mark.parametrize("raw", [b"not json", b"[]", b'{"type":"text"}', b'{"sender":"x"}', b'{"type":"text","sender":""}', b'{"type":1,"sender":"x"}'])
def test_malformed_payloads_are_400_not_500(webhook_client, raw):
    assert signed_post(webhook_client, None, raw=raw).status_code == 400


def test_invalid_base64_media_is_reported(webhook_client, bridge):
    Stubs.agent = FakeAgent()
    p = doc_msg(media_base64="!!!not-base64!!!")
    assert signed_post(webhook_client, p).status_code == 200
    assert "damaged" in bridge.texts()[0]


# ---------------------------------------------------------------------------------------------
# bridge_client
# ---------------------------------------------------------------------------------------------


def test_send_text_success(bridge):
    assert send_text(LID, "hi")["status"] == "sent"
    assert bridge.requests == [("/send-text", {"to": LID, "text": "hi"})]


def test_send_audio_payload(bridge):
    send_audio(LID, b"abc", mimetype="audio/mpeg")
    (path, body), = bridge.requests
    assert path == "/send-audio" and body["audio_base64"] == "YWJj" and body["mimetype"] == "audio/mpeg"


def test_bridge_error_carries_status_code_and_a_human_message(bridge):
    bridge.fail_with(404, "923009999999 is not registered on WhatsApp.", code="not_on_whatsapp")
    with pytest.raises(BridgeError) as e:
        send_text("923009999999", "hi")
    assert e.value.status == 404 and e.value.code == "not_on_whatsapp"
    assert "not registered on WhatsApp" in str(e.value) and "Traceback" not in str(e.value)


def test_unreachable_bridge_message_says_what_to_do(bridge):
    bridge.stop()
    with pytest.raises(BridgeError) as e:
        send_text(LID, "hi")
    assert "npm start" in str(e.value) and e.value.status is None


def test_bridge_timeout_message(monkeypatch):
    def slow(*a, **k):
        raise requests.exceptions.ReadTimeout()

    monkeypatch.setattr(requests, "post", slow)
    with pytest.raises(BridgeError, match="didn't answer"):
        send_text(LID, "hi")


def test_non_json_error_body(bridge):
    """A proxy / crashed server answering with an HTML page instead of the bridge's JSON."""
    bridge.status = 502
    bridge.raw_body = "<html>Bad gateway</html>"
    with pytest.raises(BridgeError, match="Bad gateway") as e:
        send_text(LID, "hi")
    assert e.value.status == 502 and e.value.code is None


def test_multiline_bridge_errors_are_flattened_to_one_log_line(bridge):
    bridge.fail_with(500, NO_LID)  # the real error text contains a newline
    with pytest.raises(BridgeError) as e:
        send_text(LID, "hi")
    assert "\n" not in str(e.value) and "No LID for user" in str(e.value)


def test_extract_incoming_message_valid_and_invalid():
    ok = extract_incoming_message({"type": "audio", "sender": LID, "from_me": False, "media_base64": "YWJj", "mimetype": "audio/ogg"})
    assert ok["media_bytes"] == b"abc" and ok["filename"] == "whatsapp_audio" and ok["text"] == ""
    assert extract_incoming_message({"type": "text", "sender": LID})["from_me"] is False
    assert extract_incoming_message({"type": "image", "sender": LID, "media_error": "too_large"})["media_error"] == "too_large"
    for bad in (None, [], "x", {}, {"type": "text"}, {"sender": "x"}):
        with pytest.raises(ValueError):
            extract_incoming_message(bad)
