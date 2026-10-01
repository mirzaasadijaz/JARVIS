# Jarvis

A personal AI assistant: voice (Urdu + English) locked behind a wake
word and PIN, desktop automation, WhatsApp routing, RAG over files from
WhatsApp and the computer, and a LangGraph agent brain with 35 tools
across weather, scheduling, memory, email, social posting, research,
maps, browser automation, and file editing.

Full design reasoning lives in `docs/Jarvis_Tech_Stack_Guide.md` and
`docs/Jarvis_Build_Workflow.md`. This file is just setup + running.

## Setup

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env              # then fill in your keys, including JARVIS_PIN
```

See `.env.example` for what each key is, whether it's free or paid, and
where to get it. You don't need all of them — only what the phase
you're on actually requires. Nothing in the voice lock itself needs an
account — openWakeWord's "hey_jarvis" model ships with the library, and
the PIN is just a value you pick.

**WhatsApp bridge setup** (no Docker, no database — just Node.js):
```bash
cd whatsapp_bridge
npm install
set WEBHOOK_SECRET=<same value as WEBHOOK_SECRET in your .env>   # Windows cmd; PowerShell: $env:WEBHOOK_SECRET="..."
npm start
```
A QR code prints in that terminal — scan it with WhatsApp on your
phone: **Settings → Linked Devices → Link a Device**. The session is
saved locally in `whatsapp_bridge/.wwebjs_auth/`, so you only scan once.

One-time setup script, only needed if using the Gmail tools:
```bash
python scripts/setup_gmail_oauth.py
```

## Running

Three separate, independent processes:

```bash
cd whatsapp_bridge && npm start    # connects to WhatsApp, forwards messages to Jarvis
python run_voice.py                 # the mic-listening loop — run this natively, not in Docker
python run_server.py                # the WhatsApp webhook — the only one of the three that *can* be containerized
```

Say **"jarvis"** to wake it up — a PIN popup appears; enter your
`JARVIS_PIN` to unlock. Say **"bye jarvis"** at any point during an
active conversation to shut the whole program down.

`docker-compose.yml` can run `run_server.py` in a container; both
`run_voice.py` and the WhatsApp bridge need to run directly on the
host — the former for real screen/mic/speaker access, the latter
because its saved login session is simplest to keep on local disk. See
the comment at the top of `docker-compose.yml`.

For always-on operation, `deploy/` has example systemd units for both
processes.

## Architecture

```
mic -- "jarvis" (wake word) --> PIN popup --> unlocked
    --> speech-to-text --> core/agent.py (LangGraph brain, 35 tools,
        full middleware stack) --> text-to-speech
    -- "bye jarvis" --> program exits

WhatsApp --> speech-to-text (if voice note) / text
    --> core/agent.py --> WhatsApp reply
```

Wake-word detection, the PIN prompt, STT, and TTS are NOT agent tools —
they sit outside the graph, at the input/output boundary. Everything
the agent can actually *decide* to call lives in `tools/`.

## Modules

| Folder | What's in it |
|---|---|
| `core/` | The agent itself, middleware stack, cost tracking, PIN lock, status indicator |
| `voice/` | Mic input, wake-word detection, VAD, STT, TTS, the main voice loop |
| `tools/` | Every `@tool` the agent can call — one file per capability |
| `whatsapp_server/` | The FastAPI webhook, WhatsApp bridge client, request security |
| `whatsapp_bridge/` | The Node.js process that actually holds the WhatsApp connection (whatsapp-web.js) |
| `scripts/` | One-off setup scripts (currently: Gmail OAuth) |
| `deploy/` | Example systemd units for always-on operation (Python processes only — the bridge needs its own, e.g. via `pm2` or Task Scheduler on Windows) |


## Known limitations, flagged honestly rather than hidden

- **`whatsapp_bridge/server.js`** was verified as far as this sandbox
  allows: dependencies install, syntax checks clean, and the
  HMAC-SHA256 webhook signature was cross-checked byte-for-byte against
  Python's — Node's output and Python's `verify_webhook_signature`
  agree exactly. What couldn't be tested here: actually scanning a QR
  code and holding a live WhatsApp session (this sandbox has no way to
  launch a real browser against WhatsApp's servers). That first
  `npm start` is the real first test.
- **Dictation Mode's mic session** (in `whatsapp_server/webhook.py`) is
  separate from the always-on one in `voice/loop.py`. Running both
  `run_voice.py` and `run_server.py` at once means two processes
  competing for one microphone. Needs a small handoff (e.g. a row in
  `data/jarvis.db` that `voice/loop.py` polls) — not built yet.
- **`tools/desktop.py`, `core/status.py`, and `core/pin_lock.py`** need
  a real display (PyAutoGUI, pystray, and tkinter's popup window all
  require one) and couldn't be functionally tested in the sandbox this
  was built in — only syntax-checked / import-checked. Verify on your
  actual machine. tkinter ships with standard Python on Windows, so no
  extra install should be needed there.
- **`whatsapp_server/evolution_client.py` and `tools/social.py`**
  are written to each API's documented REST conventions but couldn't
  be tested against a real running Evolution API instance or real Meta
  credentials — confirm exact endpoint paths against current docs.
