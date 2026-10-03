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

Optional bridge settings (environment variables, same way as `WEBHOOK_SECRET`):
`BRIDGE_PORT` (default 3001), `JARVIS_WEBHOOK_URL` (default
`http://localhost:8000/webhook`), `MAX_MEDIA_MB` (default 25), and
`BRIDGE_HOST` — set it to `127.0.0.1` if Jarvis and the bridge run on the
same machine, so other devices on your network can't reach the bridge's
(unauthenticated) send endpoints. Leave it unset if Jarvis runs in Docker.

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


## Troubleshooting WhatsApp

**`No LID for user`** (HTTP 500 from the bridge). WhatsApp is moving accounts
to "LID" addressing (`12345…@lid` instead of `phone@c.us`), and
whatsapp-web.js 1.34.x throws this when WhatsApp Web hasn't loaded the
phone↔LID mapping for a chat. 1.34.7 is the newest release, so upgrading
doesn't help; `whatsapp_bridge/sender.js` works around it (no implicit
mark-as-read, asks WhatsApp to resolve the contact, then retries with every
id it learns) and explains in plain words when it still can't. If you see a
`no_lid` error in the bridge log, the contact has probably never messaged
this account — ask them to send one message first.

**Which chats does Jarvis answer?** Only 1:1 chats. Groups, status updates,
channels, stickers, reactions and other things Jarvis can't act on are ignored
by the bridge, so it can't spam a group as you or post a status.

**Sensitive actions (send message/email, write files, open apps).** They need
approval (`core/middleware.py`). Over WhatsApp and voice there is nobody to
ask, so Jarvis declines and tells you it needs your confirmation; to actually
approve one, use the terminal tester: `python core/agent.py` asks y/n.

**Image attachments** are read with Tesseract OCR, a separate program. On
Windows install it from https://github.com/UB-Mannheim/tesseract/wiki — until
then Jarvis replies that it can't read images instead of failing.

**Where do errors show up?** One readable line per problem in the
`run_server.py` window (and in the bridge window); set `LOG_LEVEL=DEBUG` in
`.env` for full tracebacks.

**Tests** (no phone, API keys or network needed):
```bash
cd whatsapp_bridge && npm test      # bridge: sending, LID fallbacks, incoming-message filtering
pip install pytest && pytest        # server: webhook, reply delivery, approvals, voice, OCR
```

## Known limitations, flagged honestly rather than hidden

- **`whatsapp_bridge/`** is tested against a fake WhatsApp client that
  reproduces the library's real behaviour, including the `No LID for user`
  failures (`npm test`), and the HMAC webhook signature was cross-checked
  against Python's. What can't be tested without your phone is a live
  WhatsApp session, so the first real conversation is the final check.
- **`tools/desktop.py`, `core/status.py`, and `core/pin_lock.py`** need
  a real display (PyAutoGUI, pystray, and tkinter's popup window all
  require one) and couldn't be functionally tested in the sandbox this
  was built in — only syntax-checked / import-checked. Verify on your
  actual machine. tkinter ships with standard Python on Windows, so no
  extra install should be needed there.
- **`tools/social.py`** is written to the Meta Graph API's documented REST
  conventions but couldn't be tested against real Meta credentials —
  confirm exact endpoint paths and the API version against current docs.
- **Access control:** every 1:1 chat that messages the linked WhatsApp
  account gets an answer from the full agent. Only the tools listed in
  `core/middleware.py` (`SENSITIVE_TOOLS`) need approval; the rest run
  freely for anyone who messages the account — including `read_file`,
  `search_inbox`, `take_screenshot`, and the desktop controls `type_text`,
  `press_key` and `click_at`. `JARVIS_OWNER_NUMBER` is not enforced yet. Add
  an allow-list in `whatsapp_server/webhook.py` (and/or widen `SENSITIVE_TOOLS`)
  before linking an account you care about.
- **Docker:** the `jarvis-server` image can't start headless as written —
  `core/agent.py` imports `tools/desktop.py`, and PyAutoGUI fails on import
  without a display. Run `python run_server.py` natively (as above).
