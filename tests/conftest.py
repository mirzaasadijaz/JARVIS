"""Shared test setup.

Real: config, FastAPI app, request signing, bridge_client, core.runner, and a real
LangGraph agent (with the human-in-the-loop middleware) driven by a scripted model.
Faked: the Node bridge (a tiny local HTTP server that can answer with the exact
"No LID for user" 500), and the heavy third-party pieces — the LLM brain, Deepgram,
ElevenLabs, ChromaDB — so the tests need no API keys, no network and no hardware.

Run from the project root:   pytest -q
"""

import hashlib
import hmac
import json
import os
import sqlite3
import sys
import tempfile
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# config.Settings() insists on one brain key at import time; these tests never call a real LLM.
os.environ.setdefault("GOOGLE_API_KEY", "test-key")
os.environ["WEBHOOK_SECRET"] = "test-secret"
os.environ.setdefault("LOG_LEVEL", "INFO")

from langchain.agents import create_agent  # noqa: E402
from langchain.agents.middleware import HumanInTheLoopMiddleware  # noqa: E402
from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: E402

# ---------------------------------------------------------------------------------------------
# Stand-ins for the heavy modules whatsapp_server.webhook imports. Tests steer them via `Stubs`.
# ---------------------------------------------------------------------------------------------


class Stubs:
    agent = None
    transcribe = staticmethod(lambda audio: "")
    synthesize = staticmethod(lambda text, *a, **k: b"mp3-bytes")
    ingest = staticmethod(lambda path, source="computer": 0)


class _AgentProxy:
    def invoke(self, *a, **k):
        return Stubs.agent.invoke(*a, **k)

    def get_state(self, *a, **k):
        return Stubs.agent.get_state(*a, **k)


def _module(name, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    sys.modules[name] = mod
    return mod


_module("core.agent", agent=_AgentProxy())
_module("tools.documents", ingest_file=lambda *a, **k: Stubs.ingest(*a, **k))
_module("voice.stt", transcribe=lambda audio: Stubs.transcribe(audio))
_module("voice.tts", synthesize_speech=lambda text, *a, **k: Stubs.synthesize(text, *a, **k), SAMPLE_RATE=24000)

# ---------------------------------------------------------------------------------------------
# A scripted chat model + real agent
# ---------------------------------------------------------------------------------------------


class ScriptedModel(BaseChatModel):
    """Plays back a list of AIMessages and records what it was shown."""

    script: list = []
    seen: list = []

    @property
    def _llm_type(self):
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(list(messages))
        nxt = self.script.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return ChatResult(generations=[ChatGeneration(message=nxt)])


@tool
def send_whatsapp_message(to: str, message: str) -> str:
    """Send a WhatsApp message."""
    return f"sent to {to}"


@tool
def get_time() -> str:
    """Current time."""
    return "12:00"


@pytest.fixture
def make_agent():
    """make_agent([AIMessage, ...]) -> (real LangGraph agent with HITL + sqlite memory, model)."""
    conns = []

    def factory(script):
        conn = sqlite3.connect(os.path.join(tempfile.mkdtemp(), "t.db"), check_same_thread=False)
        conns.append(conn)
        model = ScriptedModel(script=list(script), seen=[])
        agent = create_agent(
            model=model,
            tools=[send_whatsapp_message, get_time],
            middleware=[HumanInTheLoopMiddleware(interrupt_on={"send_whatsapp_message": True})],
            checkpointer=SqliteSaver(conn),
        )
        return agent, model

    yield factory
    for c in conns:
        c.close()


# ---------------------------------------------------------------------------------------------
# Fake Node bridge
# ---------------------------------------------------------------------------------------------


class FakeBridge:
    """Stands in for whatsapp_bridge/server.js. By default every send succeeds."""

    def __init__(self):
        self.requests = []  # [(path, json_body)]
        self.status = 200
        self.body = {"status": "sent", "to": "x", "via": "direct"}
        self.raw_body = None  # set to a str to answer with non-JSON (e.g. a proxy's HTML error page)
        self._server = None

    def fail_with(self, status, error, code=None):
        self.status = status
        self.body = {"error": error, **({"code": code} if code else {})}

    def texts(self):
        return [b["text"] for p, b in self.requests if p == "/send-text"]

    def audios(self):
        return [b for p, b in self.requests if p == "/send-audio"]

    def start(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("content-length", 0))
                outer.requests.append((self.path, json.loads(self.rfile.read(length) or b"{}")))
                payload = (outer.raw_body if outer.raw_body is not None else json.dumps(outer.body)).encode()
                self.send_response(outer.status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *a):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server.server_close()


@pytest.fixture
def bridge(monkeypatch):
    from config import settings

    fake = FakeBridge()
    monkeypatch.setattr(settings, "whatsapp_bridge_url", fake.start())
    yield fake
    fake.stop()


# ---------------------------------------------------------------------------------------------
# The real FastAPI app, with signed-request helper
# ---------------------------------------------------------------------------------------------


@pytest.fixture
def webhook_client():
    from fastapi.testclient import TestClient

    from whatsapp_server.security import limiter
    from whatsapp_server.webhook import app

    limiter.reset()  # 30/minute per IP would otherwise be exhausted across tests
    Stubs.agent = None
    Stubs.transcribe = staticmethod(lambda audio: "")
    Stubs.synthesize = staticmethod(lambda text, *a, **k: b"mp3-bytes")
    Stubs.ingest = staticmethod(lambda path, source="computer": 0)
    # raise_server_exceptions=True (default): an exception escaping a background task fails the
    # test — exactly how "Exception in ASGI application" showed up in the real server log.
    return TestClient(app)


def signed_post(client, payload, secret="test-secret", raw=None):
    body = raw if raw is not None else json.dumps(payload, separators=(",", ":")).encode()
    signature = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/webhook", content=body, headers={"x-webhook-signature": signature, "content-type": "application/json"})
