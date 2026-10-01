# Jarvis — Step-by-Step Build Workflow

This is the companion to `Jarvis_Tech_Stack_Guide.md`. That file covers the *why* — which library, which API, which one's best. This file is purely the *what, in what order*: every phase, checked off in sequence, so you always know exactly what to build next and how to confirm it worked before moving on.

Each phase only depends on the ones before it — don't skip ahead, especially past Phase 1 and Phase 2, since almost everything later plugs into that core loop.

---

## Phase 0 — Environment & project setup

- [ ] Install Python 3.11+ (`python --version` to confirm)
- [ ] Install Git and a code editor (VS Code or similar)
- [ ] Create the project and initialize git:
  ```bash
  mkdir jarvis && cd jarvis
  git init
  ```
- [ ] Create and activate a virtual environment:
  ```bash
  python -m venv venv
  source venv/bin/activate      # Windows: venv\Scripts\activate
  ```
- [ ] Create the base folder structure:
  ```
  jarvis/
  ├── tools/          # one file per module — desktop.py, whatsapp.py, weather.py...
  ├── agent.py        # the LangGraph agent + middleware stack
  ├── config.py       # pydantic-settings, loads .env
  ├── .env            # every secret — never committed
  ├── .gitignore
  └── requirements.txt
  ```
- [ ] Create `.gitignore` with at minimum: `.env`, `venv/`, `__pycache__/`, `*.db`
- [ ] Install core dependencies:
  ```bash
  pip install langgraph langchain langchain-anthropic python-dotenv pydantic-settings
  ```
- [ ] Commit: `git add . && git commit -m "project skeleton"`

> ✅ **Milestone:** a git repo, a virtual environment, a folder structure. Nothing runs yet — that's expected.

---

## Phase 1 — Minimal text-only brain

Prove the core loop works before adding anything else.

- [ ] Create an Anthropic Console account, generate an API key
- [ ] Add it to `.env`: `ANTHROPIC_API_KEY=sk-...`
- [ ] Write `config.py` to load settings via `pydantic-settings`
- [ ] Write a minimal `agent.py`: `create_agent()`, no tools yet, a short system prompt, a plain terminal input loop
- [ ] **Test:** run it, type a message, confirm a sensible reply
- [ ] Sign up for OpenWeatherMap's free tier, get a key, add to `.env`
- [ ] Write your first real tool in `tools/weather.py` → `get_weather(location)`, decorated with `@tool`
- [ ] Pass `tools=[get_weather]` into `create_agent(...)`
- [ ] **Test:** ask "what's the weather in Lahore" — confirm the agent actually *calls* the tool, not just guesses an answer
- [ ] Add `checkpointer=InMemorySaver()` so it remembers earlier turns in the same run
- [ ] Add `SummarizationMiddleware` so long sessions don't blow the context window
- [ ] Commit

> ✅ **Milestone:** you can hold a typed conversation with Jarvis, and it correctly calls at least one real tool. Everything after this is addition, not foundation.

---

## Phase 2 — Voice in, voice out

- [ ] Sign up for Deepgram (comes with a $200 free credit), get an API key
- [ ] Write `tools/stt.py` → `transcribe(audio_bytes) -> str` against Deepgram's streaming endpoint
- [ ] **Test:** record a short Urdu+English mixed clip, feed it in, check the transcript
- [ ] Sign up for ElevenLabs, get an API key
- [ ] Write `tools/tts.py` → `synthesize_speech(text) -> audio`, using the Flash v2.5 model for low latency
- [ ] **Test:** pass a string in, confirm it plays back through your speakers
- [ ] Install `sounddevice` for mic capture, plus Silero VAD (or Picovoice Cobra) for voice-activity detection
- [ ] Wire the loop: mic → VAD detects speech → `transcribe()` → text goes into Phase 1's agent → `synthesize_speech()` on the reply → plays through speakers
- [ ] **Test:** a full spoken back-and-forth, out loud, no typing

> ✅ **Milestone:** you can talk to Jarvis and hear it talk back. It'll respond to *anyone's* voice right now — deliberately fixed in the next phase, so you're not debugging the voice pipeline and biometrics at the same time.

---

## Phase 3 — Add the voice lock (speaker verification)

- [ ] Create a Picovoice Console account, generate an AccessKey
- [ ] Follow Eagle's enrollment flow to create your own voice profile (a handful of recorded clips)
- [ ] Write `tools/verify.py` → `verify_speaker(audio_bytes) -> bool`
- [ ] Insert it as a gate *before* `transcribe()` runs in the main loop — if it fails, the agent is never invoked
- [ ] **Test:** your voice passes; a recording or another voice is rejected
- [ ] *(Recommended)* add Picovoice Koala noise suppression right before verification — same free-tier account as Eagle

> ✅ **Milestone:** Jarvis only responds to your voice. Everything from here runs behind this gate.

---

## Phase 4 — Desktop automation

- [ ] `pip install pyautogui mss pyperclip pygetwindow`
- [ ] Write `tools/desktop.py`: `take_screenshot()`, `click_at(x, y)`, `type_text(text)`, `press_key(key)`, `open_application(name)`, `read_clipboard()`, `write_clipboard(text)`
- [ ] Pick your "where do I click" approach — Claude's native `computer` tool (paid, least setup) or OmniParser + a local vision model (free, more setup) — and set it up
- [ ] Register the desktop tools on the agent
- [ ] Add `HumanInTheLoopMiddleware` around anything destructive (closing apps, deleting, sending) *before* testing anything real
- [ ] **Test:** start low-stakes — "open Notepad and type hello" — before trying multi-step tasks

> ✅ **Milestone:** Jarvis can see your screen and act on it for a simple, low-stakes task.

---

## Phase 5 — WhatsApp integration

- [ ] Install Docker, pull and run the Evolution API image
- [ ] Connect your personal number by scanning the QR code it generates (same as linking WhatsApp Web)
- [ ] Write a FastAPI app with a `/webhook` route to receive Evolution API events
- [ ] Add secret/signature verification middleware to that route
- [ ] Expose it via Cloudflare Tunnel, register the resulting URL as your webhook in Evolution API
- [ ] Implement **Command Mode**: messages from your own number route straight into the agent as commands
- [ ] Implement **Dictation Mode**: messages from anyone else trigger `announce_sender()` (via TTS) → listen via mic → `transcribe()` → `send_whatsapp_message()` back to that contact
- [ ] **Test** both modes end to end — ideally with a second phone as the "third party"

> ✅ **Milestone:** you can control Jarvis over WhatsApp, and it can relay messages from other people through your own voice.

---

## Phase 6 — Remaining modules (independent — build in any order)

Each of these only depends on Phase 1's agent, not on each other or on Phases 2–5:

- [ ] **Email** — Gmail API OAuth setup → `send_email` / `search_inbox` tools (or connect a Gmail MCP server instead)
- [ ] **Scheduling** — `pip install apscheduler` → `set_alarm` / `schedule_reminder` / `cancel_reminder`
- [ ] **Memory** — set up ChromaDB → `save_note` / `search_notes`
- [ ] **Social posting** — create a Meta developer app, link an Instagram Business account to your Facebook Page → `post_to_instagram` / `post_to_facebook_page`
- [ ] **Research** — Wikipedia wrapper + a SerpAPI key, or just enable Claude's native `web_search` tool
- [ ] **Browser automation** — `pip install playwright && playwright install`, then wire up `browser-use` or connect the official Playwright MCP server
- [ ] **Coding tool** — enable Claude's native `text_editor` tool, or write `read_file` / `write_file` / `apply_patch` yourself
- [ ] **Maps** — `pip install geopy` for free OpenStreetMap geocoding, or add a Google Maps Platform key for richer place data

> ✅ **Milestone:** every feature from your original spec has at least one working tool behind it.

---

## Phase 7 — Harden with middleware & safety

- [ ] Add `PIIMiddleware` for anything touching real contacts' messages
- [ ] Expand `HumanInTheLoopMiddleware`'s `interrupt_on` to cover every destructive action across every module you just built (send message, post to Instagram, delete a file, send an email)
- [ ] Add a tool-call-limit middleware to cap runaway loops
- [ ] Add `ToolRetryMiddleware` / `ModelRetryMiddleware`
- [ ] Swap `InMemorySaver` for `SqliteSaver` so state survives a restart
- [ ] Add `slowapi` rate limiting to the FastAPI webhook
- [ ] Build a simple daily cost/token counter with a hard cutoff

> ✅ **Milestone:** a bug — or a bad actor — can't make Jarvis do something destructive or run up an unbounded bill.

---

## Phase 8 — Reliability & going live

- [ ] Write a `Dockerfile` / `docker-compose.yml` for the whole stack
- [ ] Set up a process supervisor (systemd on Linux, Task Scheduler + NSSM on Windows, or a small watchdog script) so Jarvis restarts itself after a crash
- [ ] Wire up LangSmith so you can trace what the agent reasoned after anything unexpected
- [ ] Add a status indicator (`pystray` tray icon) for listening / thinking / speaking
- [ ] Run a multi-day soak test before relying on it daily
- [ ] Re-check the security notes from the Tech Stack Guide: `.env` never committed, webhook secret in place, voice profile data encrypted at rest

> ✅ **Milestone:** Jarvis runs unattended, restarts itself, and you can see what it's doing at any moment.

---

## Appendix — every account you'll create, in the order you'll need it

| Phase | Account | Free to start? |
|---|---|---|
| 1 | Anthropic Console | Yes |
| 1 | OpenWeatherMap | Yes |
| 2 | Deepgram | Yes — $200 credit |
| 2 | ElevenLabs | Yes |
| 3 | Picovoice Console | Yes |
| 5 | Docker Hub (to pull Evolution API's image) | Yes |
| 6 | Google Cloud Console (Gmail API) | Yes |
| 6 | Meta Developer + Instagram Business account | Yes |
| 6 | SerpAPI *(optional)* | Yes |
| 8 | LangSmith *(optional)* | Yes |

---

Want the actual starter code for Phase 0 and Phase 1 next — a real `agent.py`, `config.py`, and `requirements.txt` you can `pip install` and run today?
