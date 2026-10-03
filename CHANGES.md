# Jarvis — what was wrong, what changed, how it was checked

## 1. The error you reported

```
❌ Node.js Text Error: {"error":"No LID for user\ns (https://static.whatsapp.net/…)"}
requests.exceptions.HTTPError: 500 Server Error … /send-text
ERROR: Exception in ASGI application
```

Two separate problems were stacked on top of each other.

**The bridge couldn't send (`No LID for user`).** That text is thrown by WhatsApp Web
itself — inside the browser whatsapp-web.js drives — when it is asked to open or
send to a chat whose phone-number ↔ LID mapping it hasn't loaded. whatsapp-web.js
1.34.7 (the newest release, so upgrading doesn't help) can hit it in two places
inside `sendMessage`: opening the chat (`getChat → findOrCreateLatestChat`) and the
implicit "mark as read" (`sendSeen`). Your history shows how it got here: the thread
IDs in `data/jarvis.db` are `whatsapp-22952607240241` (old code, which built a fake
`…@c.us` out of a LID's digits) and `whatsapp-22952607240241@lid` (current code,
`msg.from`). That contact is LID-only — WhatsApp never gives you their phone number —
so `msg.from` was the right idea but the two fragile steps above were still in the way.
(I only read the thread IDs, not any message content.)

**The server turned that into a crash.** `bridge_client.send_text` raised `HTTPError`
inside a FastAPI *background task*. There is no caller to catch an exception there, so
it surfaced as "Exception in ASGI application" and a page-long traceback. This would
have happened for *any* delivery problem, not just this one.

## 2. What changed

Changed (14) · new (11) · unchanged (36). No new dependencies.

| File | What / why |
|---|---|
| `whatsapp_bridge/sender.js` **(new)** | The fix for `No LID for user`. Never uses the implicit mark-as-read; on the error it asks WhatsApp to resolve the contact (`getContactLidAndPhone`, added in 1.34.0 for exactly this), then retries the same id and every id the lookup reveals. Only LID errors are retried (so no double sends). Bare phone numbers are checked with `getNumberId` first → clean "not on WhatsApp" (404). A `sendMessage` that resolves `undefined` (chat couldn't be opened — the old code reported that as "sent") is now a failure. |
| `whatsapp_bridge/server.js` | Uses `sender.js`. Answers **only 1:1 chats** (before: every group message and every contact's status update was forwarded, so Jarvis could have replied into groups as you or tried to post a status). Ignores stickers/videos/locations/reactions (a location's `body` is a base64 thumbnail that was being sent to the LLM as text). Media that can't be downloaded or is too big is flagged instead of crashing the handler. 503 instead of a cryptic 500 before WhatsApp is ready. `unhandledRejection`/`uncaughtException` handlers so WhatsApp Web's internal errors can't kill the process. Ctrl+C now closes Chromium (a leftover Chromium causes "browser is already running" on the next start). `BRIDGE_HOST` option. |
| `whatsapp_bridge/package.json` | `npm test` script. |
| `whatsapp_server/bridge_client.py` | `BridgeError` with a human message ("Can't reach the WhatsApp bridge … is it running?", "923009999999 is not registered on WhatsApp …") instead of `HTTPError` + `print`. Payload parsing validates and no longer `KeyError`s. |
| `whatsapp_server/webhook.py` | **No background task can raise any more**: each catches everything, logs one readable line (`LOG_LEVEL=DEBUG` for tracebacks) and apologises to the sender when the failure was on Jarvis's side. Also fixed: transcription ran *inside* the request (blocked the server; a Deepgram error → HTTP 500 and silence); documents were written to a hard-coded `/tmp/` (doesn't exist on Windows) under a random name (RAG results were labelled with a random id) — now a private temp folder with the real, sanitised file name; empty messages were sent to the LLM (always an API error); malformed payloads were a 500, now 400; same-sender messages are processed one at a time. |
| `core/runner.py` **(new)** | `ask_jarvis()` — used by WhatsApp, voice and the terminal. See "approvals" below, plus: reply text is always a plain string (newer Gemini returns a list of content blocks, which can't be sent to WhatsApp or TTS) and an old reply can never be re-sent. |
| `core/middleware.py` | `ToolCallLimitMiddleware(thread_limit=25)` → `run_limit=25`. `thread_limit` counts over the whole life of a saved conversation; your WhatsApp/voice threads are persistent, so after 25 tool uses in total Jarvis would refuse every tool on that thread forever (shown with your exact langchain version). `run_limit` is the per-message runaway-loop guard that was intended. Your threads are at 0 of 25 today, so you hadn't hit it yet. |
| `core/agent.py` | The terminal tester (`python core/agent.py`) uses `ask_jarvis` and asks you y/n for sensitive actions. |
| `voice/loop.py` | One failed turn (STT/LLM/TTS outage, quota…) used to propagate out of `run()` and end the whole voice session; now it's printed and the loop continues. Uses `ask_jarvis`. |
| `whatsapp_server/security.py` | A non-ASCII signature header gave HTTP 500 instead of 401; docstring still described Evolution API. |
| `tools/whatsapp.py` | Failures are *returned* to the agent as text (so it can tell you "that number isn't on WhatsApp") instead of raised and blindly retried. |
| `tools/memory.py` | `save_note` and `search_notes` were each defined twice (copy-paste). |
| `tools/documents.py` | On Windows Tesseract is a separate install; without it every image failed. Now a clear message. Image file handle closed properly (Windows can't delete an open file). |
| `tools/maps.py` | geopy's default timeout is **1 second** (verified on 2.5.0), so `geocode`/`get_directions` would routinely hit `GeocoderTimedOut`. Now 10. |
| `README.md`, `.env.example` | Removed stale text (Dictation Mode, `evolution_client.py`); added troubleshooting + tests; `JARVIS_OWNER_NUMBER` and `DAILY_COST_CAP_USD` were documented as if they protect you — nothing reads them. |
| `tests/…`, `whatsapp_bridge/test/…`, `pytest.ini` **(new)** | See section 4. |

**Approvals.** Sensitive tools (`SENSITIVE_TOOLS`: send message/email, write/patch file, post, open app) *pause* the agent for approve/reject. WhatsApp and the voice loop have no way to ask, so a pause used to return an **empty reply** (an empty WhatsApp message) and leave a tool call with no result in that conversation's saved history. On the sender's next message the model was handed that dangling call (reproduced on your langgraph version) — a tool call with no result, which LLM APIs reject — so one "message Ahmed" request would break that conversation for good. Now the pause is answered with a *reject*, the model tells the user it needs their confirmation (what your system prompt already asks for), and conversations already stuck this way are healed on their next message. To actually approve something, use the terminal tester.

## 3. Every file in the project

| Status | Files |
|---|---|
| **Changed / new** | Section 2. |
| **Verified, unchanged — OK** | `config.py`, `run_server.py`, `run_voice.py`, `available_model.py`, `requirements.txt`, `core/embeddings.py`, `core/pin_lock.py`, `core/status.py`, `voice/audio_utils.py`, `voice/vad.py`, `voice/wake_word.py`, `tools/coding.py`, `tools/gmail.py`, `tools/research.py`, `tools/scheduling.py`, `tools/weather.py`, `scripts/setup_gmail_oauth.py`, `deploy/*.service`, `.gitignore`, `whatsapp_bridge/.gitignore`, `whatsapp_bridge/package-lock.json`, the four empty `__init__.py`, `docs/*`. (The ones that need a display or microphone — pin_lock, status, VAD, wake word — can only be read and import-checked here.) |
| `voice/stt.py`, `voice/tts.py` | OK — call signatures checked against your installed Deepgram 7.9.0 and ElevenLabs 2.68.0. |
| `tools/desktop.py` | OK to run (`mss.tools` import verified on mss 10.2.0); see 5.4 for `take_screenshot`. Harmless unused `import io`. |
| `tools/social.py` | OK; Graph API v21.0 is valid until 21 Jan 2027 (current is v26.0). |
| `tools/browser.py` | OK; see 5.5. |
| `core/cost_tracker.py` | Correct, but nothing calls it — see 5.7. |
| `Dockerfile`, `docker-compose.yml` | Syntax fine; the server image can't start — see 5.3. |

Every Python file compiles, `pyflakes` is clean apart from that unused import, and all 34 third-party modules the project imports exist in your venv.

## 4. How it was checked

- **Reproduced first.** Your original code, run against a bridge that answers exactly as in your log, prints the same `❌ Node.js Text Error … No LID for user` line and dies with the same `HTTPError … /send-text`. The same scenario on the fixed code passes.
- **Bridge — `cd whatsapp_bridge && npm test` (30 tests).** A fake WhatsApp client modelled on the library source reproduces both places `No LID for user` is thrown. Removing any part of the fix (forcing `sendSeen:false`, the lookup-and-retry, "retry only LID errors", "falsy result = failure") makes tests fail.
- **Server — `pytest` (69 tests).** Real FastAPI app and request signing, real `bridge_client`, a real LangGraph agent with the approval middleware, a fake of the Node bridge, a real Tesseract run (and the Tesseract-missing case).
- **Both halves together.** The real `server.js` and the real FastAPI app as two processes over real HTTP: LID text with a broken mark-as-read, an unknown `@c.us` contact, a voice note round-trip, a document, groups/status/stickers ignored, an LLM outage, an undeliverable chat, a number not on WhatsApp — 13/13 checks, no traceback, neither process crashed.
- **Not verifiable from here:** a live WhatsApp session. Your first real message is the final check.

## 5. Found, not changed — your decision

1. **Anyone who messages the linked WhatsApp account gets the full agent.** Only `SENSITIVE_TOOLS` need approval; `read_file`, `search_inbox`, `take_screenshot`, `read_clipboard`, the browser tools and the desktop controls `type_text` / `press_key` / `click_at` run freely. So any contact (or stranger) could have Jarvis read a file or your inbox and send it back, or drive your keyboard and mouse. `JARVIS_OWNER_NUMBER` exists but is not used. Cheapest fix: an allow-list of chat ids in `webhook.py` (the bridge log shows each sender's id, e.g. `22952607240241@lid`); then widen `SENSITIVE_TOOLS`.
2. **`send_email` can't get an address you type.** `PIIMiddleware("email", strategy="redact", apply_to_input=True)` replaces it before the model sees it (verified: the model receives `email [REDACTED_EMAIL] that the invoice is ready`). Keep it for privacy, or remove it to make email work.
3. **Docker:** the `jarvis-server` image can't start headless — `core/agent.py` imports `tools/desktop.py` and PyAutoGUI raises `KeyError: 'DISPLAY'` on import. Run `python run_server.py` natively (as you do).
4. **`take_screenshot`** returns the whole PNG as base64 *text* — far beyond any model's context window. Save to a file and return the path, or return an image content block.
5. **`tools/browser.py`** keeps Playwright objects in module globals; Playwright's sync API is bound to the thread that created it, and the server runs each message on a worker thread, so a second browser call may fail with a "different thread" error. (Likely; not testable here.)
6. **Voice replies are MP3.** WhatsApp voice notes are normally OGG/Opus and the library doesn't transcode, so some phones may show but not play them. ElevenLabs can output Opus; I left it because I can't test playback. (The MIME type is now the standard `audio/mpeg`, not `audio/mp3`.)
7. **`DAILY_COST_CAP_USD`** isn't enforced: `core/cost_tracker.py` is never called.
8. **Bridge REST API is unauthenticated and listens on all interfaces.** If everything runs on one PC, set `BRIDGE_HOST=127.0.0.1` for the bridge. I left the default alone because Docker needs it open.
9. If you switch the brain to Anthropic: `claude-sonnet-5` still works but is now the legacy model; current is `claude-sonnet-5-5`.

## 6. First live run

1. `cd whatsapp_bridge && npm start` → wait for `WhatsApp bridge is connected and ready.`
2. `python run_server.py`, then message the linked number from another phone. The bridge prints `[in] text from …`, the server prints `POST /webhook 200`, the reply arrives.
3. If a reply still can't be delivered you'll now see one line in each window; the bridge's line lists every attempt, e.g. `[out] send-text failed (502 no_lid): … Tried: direct … | retry-after-lookup …`. Send me that line.
4. Your existing conversations are kept (thread IDs are unchanged).
