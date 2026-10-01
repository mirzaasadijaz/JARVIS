# Jarvis — Complete Technical Stack Guide

A module-by-module breakdown of every Python library and external API you need, with a pick for "best," and clear **Free / Freemium / Paid** labels. Pricing was checked live in August 2026, since several of these (Google Maps, Google's search API, WhatsApp, Claude) changed their pricing models within the last year.

**Legend:** 🟢 Free (no card, no meaningful limit for personal use) · 🟡 Freemium (usable free tier, pay to scale) · 🔴 Paid (card required from day one)

---

## 0. Architecture at a glance

The diagram above shows the shape of the whole system: two entry points (mic, WhatsApp) → speaker verification gate → speech-to-text → a single LangGraph "brain" → a router that fans out into your tool modules → a spoken or WhatsApp reply. Everything below is organized around that same spine.

---

## 1. The brain — orchestration + LLM

This is the reasoning core everything else plugs into.

| Tool | Type | Cost | Notes |
|---|---|---|---|
| **LangGraph** | Python lib | 🟢 Free | Open-source graph-based agent orchestration from the LangChain team. `pip install langgraph`. This is the right tool for "LLM decides which tool to call" loops — it's built for exactly this. |
| **LangChain** | Python lib | 🟢 Free | Complements LangGraph — tool wrappers, memory helpers, document loaders. |
| **Claude API** | LLM API | 🔴 Paid, usage-based | See table below. |
| **OpenAI API (GPT-5.x)** | LLM API | 🔴 Paid, usage-based | Comparable agentic/tool-calling ability; GPT-5.4 also ships native computer-use. |
| **Ollama + local model** (Llama, Qwen, DeepSeek) | Local runtime | 🟢 Free | Runs on your own GPU. Zero API cost, full privacy, but weaker tool-use reliability and noticeably weaker Urdu fluency than the frontier cloud models. |

**Claude API pricing** (per million tokens, input/output — checked against Anthropic's official pricing page):

| Model | Input | Output | Best for |
|---|---|---|---|
| Haiku 4.5 | $1 | $5 | Fast routing, simple intent classification |
| Sonnet 5 | $2 | $10 | **Best default for an assistant brain** — this became the permanent price in August 2026 (was meant to rise to $3/$15, Anthropic cancelled that increase) |
| Opus 5 / Opus 4.8 | $5 | $25 | Harder multi-step reasoning |
| Fable 5 | $10 | $50 | Most capable, rarely needed for a personal assistant |

Prompt caching cuts repeat input (system prompt, tool schemas) to 10% cost; the Batch API gives 50% off for anything non-interactive (e.g., nightly summarization).

**Why this matters for Jarvis specifically:** the Claude API now ships tool-use features that map directly onto three of your feature bullets, which could simplify your architecture a lot:
- **Computer use** (`computer_toolset_20260801`) — native screenshot-and-click control, standard token pricing + ~4,500 input tokens overhead per request plus image costs. Covers your "Agentic Desktop Automation" bullet without you having to glue together a separate vision model.
- **Browser use** (`browser_toolset_20260801`) — native browser control (click, type, read page text/accessibility tree), ~6,600 input token overhead. Covers your "jarvis do, fetch html code" bullet directly.
- **Code execution** — free when combined with web search/fetch; otherwise 1,550 free container-hours/month per org, then $0.05/hour. A serious alternative to E2B for the "secure code execution" bullet.
- **Web search** (server-side tool) — $10 per 1,000 searches, covers your "Research Helper" bullet with zero extra plumbing.

You don't have to use these — the DIY open-source paths below work fine and cost less at low volume — but they're worth knowing about since they can replace several rows in this table with one API you're already paying for.

*For which of the modules below already have a ready-made tool integration versus which ones you have to code yourself, see "Built-in tools vs. tools you build yourself" after the module list.*

---

## 2. Biometric voice lock (speaker verification)

| Tool | Cost | Notes |
|---|---|---|
| **Picovoice Eagle** ⭐ | 🟡 Freemium | Free tier: **100 minutes/month**, on-device, no card required. Paid tiers unlock 10,000 min/month. This is what you already specced, and it's a good pick: Azure's competing Speaker Recognition service was discontinued in September 2025, and Amazon Connect Voice ID was discontinued in May 2026 — Eagle is now one of the only production-grade, cross-platform options left. |
| SpeechBrain / pyannote.audio | 🟢 Free, open source | Self-hosted speaker verification models. Free and fully private, but noticeably higher error rates and no official cross-platform SDK — fine for experimentation, riskier for a "reject unauthorized voices" security gate. |

**Recommendation:** stick with Eagle. For a single-user personal assistant, 100 free minutes/month of *verification* audio (a few seconds per command, not continuous) is very unlikely to run out. Pair it with **Picovoice Cobra** (free tier, voice activity detection) so you're not running verification on silence or background noise.

---

## 3. Speech-to-text (Urdu + English)

| Tool | Cost | Urdu support | Latency |
|---|---|---|---|
| **Deepgram Nova-3** ⭐ | 🟡 Freemium | Added Feb 2026 as a production monolingual model; Nova-3 also does **real-time multilingual code-switching** (mixing languages mid-stream) across its multilingual model set | Sub-300ms streaming — genuinely "ultra-low latency" |
| OpenAI Whisper (self-hosted via `faster-whisper`) | 🟢 Free, open source | Supports Urdu; quality is decent but Whisper treats Urdu as a lower-resource language, so accuracy trails Deepgram/Google | Higher latency, esp. on CPU |
| Google Cloud Speech-to-Text | 🔴 Paid | Strong Urdu (`ur-PK`/`ur-IN`) support | Good |
| ElevenLabs Scribe | 🟡 Freemium | Supports Urdu, but Urdu sits in ElevenLabs' own "Good" accuracy tier (10–25% WER) rather than their top tier | Good |

Deepgram pricing: roughly **$0.0043/min pre-recorded, $0.0048–0.0077/min streaming** (~$0.26–0.46/hour), with a **$200 free credit** on signup and no card required — that's over 40,000 minutes of free transcription before you pay anything.

**Recommendation:** Deepgram Nova-3 for the live voice pipeline (Urdu support + native code-switching + sub-300ms latency is a near-perfect match for your "mixing English and Urdu seamlessly... without rigid trigger words" requirement). Run `faster-whisper` locally as a free offline fallback for when you don't want to hit the network, or for batch-transcribing WhatsApp voice notes where latency doesn't matter.

---

## 4. Text-to-speech (Urdu + English, emotive)

| Tool | Cost | Urdu voice | Notes |
|---|---|---|---|
| **ElevenLabs** ⭐ | 🟡 Freemium | Yes — ElevenLabs has a dedicated Urdu TTS offering with adjustable regional accents | Free tier: 10,000 characters/month. Flash v2.5 model does ~75ms latency across 32 languages; Eleven v3 is the most emotionally expressive model (70+ languages). Paid tiers run roughly $5–$299/month by volume. |
| **Azure Neural TTS** | 🟡 Freemium | Yes — two dedicated Urdu (Pakistan) neural voices: `ur-PK-UzmaNeural` (female) and **`ur-PK-AsadNeural`** (male) — a fun coincidence given your own name | 140+ languages, 400+ voices total. Standard neural voices are billed per character (cheaper tier); HD voices are $22 per 1M characters as of March 2026. |
| `edge-tts` (unofficial, wraps Microsoft Edge's TTS) | 🟢 Free | Yes, via Edge's Urdu voices | No API key needed, but it's an unofficial wrapper — fine for a personal project, not something to depend on for anything commercial |
| Coqui TTS | 🟢 Free, open source | Limited/self-trained | Fully local, more setup work |

**Recommendation:** ElevenLabs Flash v2.5 for real-time replies (low latency, genuinely emotive delivery), with Azure's `ur-PK-AsadNeural` as a strong, cheaper-at-scale alternative specifically tuned for Urdu. Use `edge-tts` as a zero-cost fallback while you're still building.

---

## 5. Wake word / voice activity detection

Your spec explicitly wants to avoid "rigid trigger words," which points toward VAD-driven listening rather than a wake word — but a wake word is still useful as a cheap first filter before you spend money on STT/verification.

| Tool | Cost | Notes |
|---|---|---|
| **Picovoice Cobra** (VAD) | 🟡 Freemium | Free tier included alongside Eagle in the same Picovoice account |
| **Silero VAD** | 🟢 Free, open source | Fully local, no account needed, very lightweight |
| **Picovoice Porcupine** (wake word) | 🟡 Freemium | Free: 1 monthly active user — plenty for personal use, if you want an optional "Jarvis" trigger word alongside always-on VAD |

---

## 6. Agentic desktop automation (computer use)

| Tool | Type | Cost | Notes |
|---|---|---|---|
| **PyAutoGUI** | Python lib | 🟢 Free | Mouse/keyboard control, screenshots. `pip install pyautogui` |
| **pyperclip** | Python lib | 🟢 Free | Clipboard read/write |
| **subprocess** | stdlib | 🟢 Free | Launching applications |
| **mss** | Python lib | 🟢 Free | Fast multi-monitor screenshots (faster than PyAutoGUI's built-in) |
| **Pillow / OpenCV** | Python lib | 🟢 Free | Image processing, template matching for "find this button" without an LLM |
| **pygetwindow** | Python lib | 🟢 Free | Window management (focus, move, resize) |
| **OmniParser** (Microsoft) | Model + lib | 🟢 Free, open source | Parses a screenshot into structured, clickable UI elements — a strong free complement to any vision LLM for "locate this button" |
| **Claude computer-use tool** | API tool | 🔴 Paid | Native screenshot → click/type/scroll loop, see §1 |
| **GPT-5.4 computer use** | API tool | 🔴 Paid | OpenAI's equivalent; scored 75% on the OSWorld-Verified desktop-agent benchmark |

**Recommendation:** `PyAutoGUI` + `mss` + `pyperclip` for the actual mouse/keyboard/clipboard actions (all free, all local), driven by either **Claude's or GPT's native computer-use tool** for the "where do I click" reasoning — this is genuinely one of the harder problems in the whole project, and a frontier vision-capable model earns its cost here. If you want a fully free pipeline, pair `OmniParser` (free, extracts UI elements from a screenshot) with a locally-run vision model instead.

---

## 7. WhatsApp — routing, command mode, dictation mode

| Tool | Cost | Notes |
|---|---|---|
| **Evolution API** ⭐ | 🟢 Free, self-hosted | Open-source REST gateway (Node.js/TypeScript) built on the Baileys library, actively maintained. Connects via the WhatsApp Web protocol using your *existing personal number* — no business verification needed. Supports voice messages, media, and webhooks out of the box, which is exactly your "Command Mode / Dictation Mode" design. |
| WhatsApp Business Platform (Cloud API, official) | 🟡 Freemium | Platform access itself is free. **Replies inside a 24-hour customer-initiated window are free** — which covers your Dictation Mode use case (someone messages Asad, Jarvis replies within the window) almost entirely. You'd only pay if Jarvis proactively sent template messages (marketing/utility/auth) outside that window, at rates that vary by recipient country (roughly $0.01–$0.06/message). Requires a registered WhatsApp Business number, separate from your personal one. |
| **FastAPI + Uvicorn** | Python lib | 🟢 Free | Webhook receiver for Evolution API events |
| ngrok / Cloudflare Tunnel | Freemium/Free | 🟡 / 🟢 | To expose your local FastAPI webhook to Evolution API's server. Cloudflare Tunnel is fully free with no session limits. |

**Important caveat:** Evolution API's Baileys connection is an unofficial, reverse-engineered protocol — it works on your real personal WhatsApp number, which is exactly what you want for "Command Mode," but it technically falls outside WhatsApp's Terms of Service and carries a small risk of the number being flagged if used heavily or erratically. For a personal assistant sending/receiving normal-volume messages this risk is low in practice, but it's worth knowing. The official Cloud API is the zero-risk alternative, at the cost of needing a *second*, separate business-registered number.

**Recommendation:** Evolution API for your actual personal number (matches the "Command Mode from Asad's personal number" design exactly, and is free). Keep the official Cloud API in your back pocket if you ever want a second, fully compliant number for anything more automated.

---

## 8. Autonomous task orchestration

| Tool | Type | Cost | Notes |
|---|---|---|---|
| **LangGraph** | Python lib | 🟢 Free | Covered in §1 — this is your actual orchestration layer |
| **APScheduler** | Python lib | 🟢 Free | Alarms, reminders, recurring jobs. `pip install apscheduler` |
| **SQLite** | stdlib | 🟢 Free | Local state, task queue, conversation memory |
| **E2B Sandbox** | API | 🟡 Freemium | Free "Hobby" tier: **$100 one-time credit**, 20 concurrent sandboxes, 1-hour sessions, no card required. Pro tier is $150/month for 24-hour sessions. Usage-billed at ~$0.05/vCPU-hour beyond that. Open-source core, self-hostable if you want $0 forever. |
| Claude's built-in code execution tool | API tool | 🟡 Freemium | Free when paired with web search/fetch tool calls in the same request; otherwise 1,550 free container-hours/month per org, then $0.05/hour |

**Recommendation:** LangGraph + APScheduler + SQLite for the core loop (all free), E2B's free Hobby tier for anything that needs real sandboxed code execution (data analysis, running generated scripts safely) — the $100 one-time credit and 20 concurrent sandboxes are very generous for single-user use and you're unlikely to need the Pro tier.

---

## 9. Email management

| Tool | Cost | Notes |
|---|---|---|
| **Gmail API** (`google-api-python-client`) | 🟢 Free | Quota-based (plenty for personal use), needs OAuth setup once |
| `imaplib` / `smtplib` | 🟢 Free, stdlib | Works with any provider, simpler but less structured than the Gmail API |

---

## 10. Notes, memory & retrieval

| Tool | Cost | Notes |
|---|---|---|
| **SQLite** | 🟢 Free | Structured notes, task history |
| **ChromaDB** | 🟢 Free, open source | Local vector database for semantic memory / RAG over past conversations and notes |
| `sentence-transformers` | 🟢 Free, open source | Local embeddings for ChromaDB — no API cost |
| Voyage AI / OpenAI embeddings | 🔴 Paid | Higher quality embeddings if local ones aren't good enough |

---

## 11. Social media & business posting

| Tool | Cost | Notes |
|---|---|---|
| **Meta Graph API** (Facebook Pages + Instagram) | 🟢 Free API access | The API itself has no fee — you just need a Facebook Page, an Instagram **Business or Creator** account linked to it, a Meta developer app, and (for full posting permissions in production) an app review. This is the compliant, ToS-safe path you already specified. |
| `requests` | 🟢 Free | You can call the Graph API directly with plain HTTP — no SDK strictly required |
| `facebook-business` SDK | 🟢 Free | Official Python SDK, saves some boilerplate |

---

## 12. Research helper

| Tool | Cost | Notes |
|---|---|---|
| **Wikipedia** (`wikipedia-api` or direct REST) | 🟢 Free | No key needed for reasonable use |
| **Claude's web_search tool** | 🔴 Paid | $10 per 1,000 searches + token costs — very clean if you're already on the Claude API for the brain |
| **SerpAPI** | 🟡 Freemium | Free tier ~100–250 searches/month depending on current plan; paid from $25/month for 1,000 searches up to $275/month for 30,000. Handles Google, Bing, YouTube and more with structured JSON. |
| `duckduckgo-search` (unofficial) | 🟢 Free | No key, no official support, can break without notice — fine for a hobby project |

⚠️ **Don't build on Google's Custom Search JSON API** — as of 2026 it's **closed to new customers** and scheduled to stop serving entirely on January 1, 2027. Any tutorial that recommends it is out of date.

**Recommendation:** if your brain is already Claude, its built-in `web_search` tool is the least plumbing for the money. If you want a free-first stack, `wikipedia-api` + `duckduckgo-search` covers most personal research asks, with SerpAPI's free tier as backup for anything that specifically needs Google-quality results.

---

## 13. Browser automation ("Jarvis, do this")

| Tool | Type | Cost | Notes |
|---|---|---|---|
| **Playwright** ⭐ | Python lib | 🟢 Free | Modern, reliable, handles clicking/typing/scrolling/fetching HTML. Recommended over Selenium for a new project — better async support, fewer flaky waits. |
| **browser-use** | Python lib | 🟢 Free, open source | An agentic wrapper on top of Playwright specifically built for "LLM controls a browser in natural language" — very close to your "jarvis do, by fetch html code" spec out of the box |
| Selenium | Python lib | 🟢 Free | Older, still works, more boilerplate than Playwright |
| **Claude's browser-use tool** | API tool | 🔴 Paid | Native browser control tool, standard tool pricing + ~6,600 input tokens overhead per request (see §1) |

**Recommendation:** `browser-use` (free, open source) sitting on top of Playwright is close to a drop-in for exactly what you described. If you're already paying for Claude's computer-use tool for desktop automation, its browser-use counterpart is a natural, if pricier, alternative.

---

## 14. Coding tool ("write this code, apply it")

This doesn't need new infrastructure — it's your existing LLM API plus file I/O:

| Tool | Cost | Notes |
|---|---|---|
| Claude or GPT API (same as §1) | 🔴 Paid | Generates the code/diff |
| **Claude's text-editor tool** | 🔴 Paid | Purpose-built for "view a file, make a precise edit" — standard tool pricing + ~700 input tokens overhead per request. Much more reliable than asking a model to regenerate a whole file from scratch. |
| Python file I/O (`pathlib`, `open()`) | 🟢 Free, stdlib | If you're driving this yourself rather than via Claude's tool |

---

## 15. Maps & weather

| Tool | Cost | Notes |
|---|---|---|
| **OpenWeatherMap** ⭐ | 🟡 Freemium (very generous) | Classic endpoints (current weather, 5-day forecast, air pollution, geocoding): **60 calls/minute, up to 1,000,000 calls/month, free, no card**. The newer "One Call 3.0/4.0" product is separate and requires a card even for its free 1,000 calls/day — stick to the classic endpoints for a personal assistant. |
| **Google Maps Platform** | 🟡 Freemium | Google removed the old flat $200/month credit in March 2025. It's now per-API free tiers — e.g. ~10,000 free geocoding requests/month, ~28,500 free map loads/month, Places Autocomplete free at any volume (only the follow-up "Details" call is billed). Plenty for personal use, but worth knowing the old "$200 free credit" advice you'll find online is outdated. |
| **OpenStreetMap + Nominatim** (`geopy`) | 🟢 Free | Fully free geocoding/reverse-geocoding on public data, no key required (respect their usage policy — one request/second) |
| OpenRouteService | 🟡 Freemium | Free-tier turn-by-turn routing/directions if you want that without Google |

**Recommendation:** OpenWeatherMap's classic free tier is essentially unlimited for one person and needs no card — use it as-is. For maps, start with OpenStreetMap + `geopy` (completely free) and only reach for the Google Maps Platform if you specifically need its richer Places/business data — the free tier is fine for personal use.

---

## Master summary table

| # | Component | Best pick | Type | Cost |
|---|---|---|---|---|
| 1 | Orchestration | LangGraph | Library | 🟢 Free |
| 1 | LLM brain | Claude Sonnet 5 | API | 🔴 $2 / $10 per MTok |
| 2 | Voice lock | Picovoice Eagle | API/SDK | 🟡 Free ≤100 min/mo |
| 3 | Speech-to-text | Deepgram Nova-3 | API | 🟡 ~$0.0043–0.0077/min, $200 free credit |
| 4 | Text-to-speech | ElevenLabs Flash v2.5 | API | 🟡 Free 10k chars/mo |
| 5 | VAD / wake word | Silero VAD + Porcupine | Library/API | 🟢 / 🟡 Free |
| 6 | Desktop automation | PyAutoGUI + Claude computer-use | Library + API | 🟢 + 🔴 |
| 7 | WhatsApp | Evolution API | Self-hosted | 🟢 Free |
| 8 | Code sandbox | E2B Hobby | API | 🟡 Free ($100 credit) |
| 9 | Email | Gmail API | API | 🟢 Free |
| 10 | Memory | ChromaDB + SQLite | Library | 🟢 Free |
| 11 | Social posting | Meta Graph API | API | 🟢 Free |
| 12 | Research | Wikipedia API + Claude web_search | API | 🟢 / 🔴 $10/1k searches |
| 13 | Browser automation | browser-use (on Playwright) | Library | 🟢 Free |
| 14 | Code editing | Claude text-editor tool | API tool | 🔴 Token-priced |
| 15 | Weather | OpenWeatherMap | API | 🟢 Free ≤1M calls/mo |
| 15 | Maps | OpenStreetMap / Nominatim | API | 🟢 Free |

---

## Built-in tools vs. tools you build yourself

Everything above is a library or an API. This section is the layer in between: how does any of it actually become a "tool" your LangGraph brain can decide to call mid-conversation? There are three sources, and knowing which one applies to each module changes how much code you personally have to write.

### Source 1 — the LLM API's own native tools (no LangChain code at all)

If your brain calls the Claude API directly, several tools are already built into the API itself — you just declare them in the request and Anthropic runs them server-side: `web_search`, `web_fetch`, `code_execution`, `computer_use`, `browser_use`, `text_editor`, `bash`. Zero implementation work on your end. This is the cheapest tier to build against, and it's why §1 flags Claude's native tools against several modules above.

### Source 2 — MCP servers (a few lines of connection code, no per-tool wrappers)

**Worth flagging clearly, since older tutorials will steer you wrong here:** LangChain's old grab-bag package, `langchain-community` — the one that used to ship ready-made wrappers for Wikipedia, Gmail, the Playwright browser, weather APIs, and dozens of others — was **officially sunset by the LangChain team in 2026**. It still installs and technically runs, but it's frozen: no new integrations, limited maintenance. Any guide (including older training data — mine included) that casually says "just `from langchain_community.tools import X`" is describing a path that's no longer where the ecosystem is headed.

The replacement is **MCP (Model Context Protocol)**: a service exposes an "MCP server," you connect to it once, and every tool it offers becomes available to your agent automatically — no per-tool code to write. Bridge MCP servers into LangGraph with:

```bash
pip install langchain-mcp-adapters
```
```python
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({
    "gmail": {"url": "http://localhost:PORT/mcp", "transport": "streamable_http"},
})
tools = await client.get_tools()  # every Gmail action, zero wrapper code written
```
(Check the current `langchain-mcp-adapters` docs before copying this verbatim — this library moves fast and exact syntax shifts between versions.)

Concretely, for Jarvis: **Gmail** and **browser control** (Microsoft publishes an official Playwright MCP server) both already have solid MCP servers, so those two modules may need close to zero custom tool code — just a connection. Check the official MCP server directory before hand-writing a wrapper for anything; there's a real chance someone already built it.

### Source 3 — tools you build yourself (`@tool` decorator)

For everything with no native API support and no good MCP server — which, for Jarvis, is most of the project (Picovoice Eagle, Evolution API, PyAutoGUI actions, Meta Graph API posting, APScheduler jobs, and Maps/Weather unless you find an MCP server for them) — you write a plain Python function and decorate it. This part of LangChain, `langchain_core.tools`, is stable and *not* part of the sunset:

```python
from langchain_core.tools import tool
import requests

@tool
def send_whatsapp_message(to: str, message: str) -> str:
    """Send a WhatsApp text message to a contact via Evolution API."""
    r = requests.post(
        f"{EVOLUTION_API_URL}/message/sendText/{INSTANCE_NAME}",
        headers={"apikey": EVOLUTION_API_KEY},
        json={"number": to, "text": message},
    )
    return "sent" if r.ok else f"failed: {r.text}"
```

Pass a list of these into LangGraph's prebuilt `create_react_agent` (or your own tool node), and the LLM can call them exactly like a built-in or MCP tool — it can't tell the difference.

### One architectural note that trips people up

Not everything in the pipeline is a "tool" the LLM chooses to call. **Speaker verification, STT, and TTS aren't tools** — they sit at the input/output boundary of the loop: verify the speaker → transcribe → *hand the text to the agent, which calls tools as it reasons* → synthesize the final reply as speech. Wrapping Eagle as an `@tool` would let the model decide *whether* to check who's speaking, which defeats the entire point of a security gate. Keep those three as plain function calls in your main loop, outside the graph — not tools inside it.

### Quick reference — which source covers which module

| Module | Tool source |
|---|---|
| Voice lock (Eagle) | *Not a tool* — runs before the agent, as a gate |
| STT / TTS | *Not a tool* — input/output boundary of the loop |
| Desktop automation | Custom `@tool` (PyAutoGUI), or Claude's native `computer_use` |
| WhatsApp (Evolution API) | Custom `@tool` |
| Code sandbox (E2B) | E2B publishes an official MCP server |
| Email (Gmail) | MCP — several actively maintained Gmail MCP servers exist |
| Memory (ChromaDB) | Custom `@tool` wrapping a retriever — a few lines |
| Social posting (Meta Graph) | Custom `@tool` |
| Research | Claude's native `web_search`, or a custom `@tool` |
| Browser automation | MCP (official Playwright MCP server), or Claude's native `browser_use` |
| Coding tool | Claude's native `text_editor` tool, or a custom `@tool` around file I/O |
| Weather / Maps | Custom `@tool` — no widely-adopted MCP server for these yet |
| Scheduling (APScheduler) | Custom `@tool` |

### Every built-in tool, by name

**Straight from the Claude API** (zero implementation if your brain calls Claude directly):

| Tool name | What it does |
|---|---|
| `web_search` | Searches the web, returns cited results |
| `web_fetch` | Retrieves and reads one specific URL |
| `code_execution` | Runs Python in a sandboxed container |
| `computer` | Screenshot, click, type, scroll, key-press — full desktop control |
| `browser` | Navigate, click, type, read a real browser page |
| `text_editor` | View a file / make a precise edit to it |
| `bash` | Runs shell commands |

**From MCP servers** (connect once, every tool the server exposes becomes available — confirmed current, since these change):

| MCP server | Representative tool names | Covers |
|---|---|---|
| **Playwright MCP** (official, Microsoft) | `browser_navigate`, `browser_click`, `browser_type`, `browser_snapshot`, `browser_take_screenshot`, `browser_press_key`, `browser_tab_new`, `browser_file_upload`, `browser_pdf_save` — 40+ tools total | Browser automation |
| **Filesystem MCP** (official reference server) | `read_file`, `write_file`, `list_directory`, `search_files`, `move_file`, `create_directory` | Coding tool, notes |
| **Gmail MCP** (several community servers, no single official one) | typically `send_email`, `search_emails`, `get_email`, `create_draft`, `list_labels` — exact names vary by which server you pick | Email |
| **E2B MCP** | run code, manage sandbox lifecycle | Code sandbox |

### Every custom tool, by name — your actual build checklist

Everything below is a plain Python function you write and decorate with `@tool` from `langchain_core.tools`, since nothing built-in covers it.

- **Desktop:** `take_screenshot()` · `click_at(x, y)` · `type_text(text)` · `press_key(key)` · `open_application(name)` · `read_clipboard()` · `write_clipboard(text)`
- **WhatsApp:** `send_whatsapp_message(to, text)` · `send_whatsapp_voice_note(to, audio_path)` · `announce_sender(name, preview)` (Dictation Mode)
- **Scheduling:** `set_alarm(time, label)` · `schedule_reminder(when, message)` · `list_reminders()` · `cancel_reminder(id)`
- **Memory:** `save_note(text)` · `search_notes(query)`
- **Social media:** `post_to_instagram(caption, image_path)` · `post_to_facebook_page(message)`
- **Maps/weather:** `get_weather(location)` · `get_forecast(location, days)` · `geocode(address)` · `get_directions(origin, destination)`
- **Voice pipeline** *(not agent tools — plain functions in your main loop, outside the graph)*: `verify_speaker(audio)` · `transcribe(audio)` · `synthesize_speech(text)`

---

## Middleware

"Middleware" means two different things here, at two different layers — and Jarvis needs both.

### 1. Agent middleware — runs inside the LangGraph loop itself

LangChain's `create_agent` API runs middleware hooks before/after the model call and before/after each tool call. This is the layer that turns a bare tool-calling loop into something safe to leave running unattended:

| Middleware | What it does | Why Jarvis specifically needs it |
|---|---|---|
| **`HumanInTheLoopMiddleware`** | Pauses and requires explicit approval before named tools run | Your second line of defense for "sensitive commands" — set `interrupt_on={"send_whatsapp_message": True, "post_to_instagram": True, "delete_file": True}` so those actions need confirmation even after the voice is already verified |
| **`SummarizationMiddleware`** | Auto-compresses older turns once token count crosses a threshold | Jarvis runs all day — without this, a long day of use eventually blows the context window |
| **`PIIMiddleware`** | Detects/redacts personal data (emails, numbers) | Relevant since Jarvis reads real WhatsApp messages from real contacts |
| A tool-call-limit middleware | Caps tool calls per turn | Safety net against a runaway loop during desktop automation |
| **`ToolRetryMiddleware`** / **`ModelRetryMiddleware`** | Auto-retries a failed tool/model call with backoff | Absorbs ordinary network hiccups from Deepgram/ElevenLabs/Evolution API |
| `AnthropicPromptCachingMiddleware` | Automatic prompt caching | Cuts repeat-token cost by ~90% if your brain is Claude |

```python
from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware, HumanInTheLoopMiddleware, PIIMiddleware
from langgraph.checkpoint.memory import InMemorySaver

agent = create_agent(
    model="claude-sonnet-5",
    tools=[send_whatsapp_message, post_to_instagram, take_screenshot],
    middleware=[
        SummarizationMiddleware(model="claude-haiku-4-5", max_tokens_before_summary=4000, messages_to_keep=20),
        PIIMiddleware("email", strategy="redact", apply_to_input=True),
        HumanInTheLoopMiddleware(interrupt_on={"send_whatsapp_message": True, "post_to_instagram": True}),
    ],
    checkpointer=InMemorySaver(),  # swap for SqliteSaver to persist across restarts
)
```

That `checkpointer` argument deserves its own callout: LangGraph persists the whole conversation/tool-call state for you — free, built in. `InMemorySaver` for one running session, `SqliteSaver`/`PostgresSaver` if Jarvis should remember where it was after a PC restart.

### 2. Web middleware — sits in front of your FastAPI webhook

The more familiar meaning: code that runs on every incoming HTTP request before your handler sees it. Your WhatsApp webhook needs this layer since it's exposed to the public internet:

| Middleware | Library | Why |
|---|---|---|
| **Signature/secret verification** | plain FastAPI dependency | Reject any webhook call missing your shared secret — otherwise anyone who finds the URL can send Jarvis fake commands |
| **Rate limiting** | `slowapi` 🟢 free | Caps requests per source, so a bug or attacker can't trigger runaway paid-API usage |
| **Request logging** | FastAPI's middleware hook 🟢 free | A record of every webhook call, for debugging |
| **Exception handling** | FastAPI exception handlers 🟢 free | One malformed payload shouldn't crash the whole server |
| CORS | `CORSMiddleware` | Only needed if you add a browser-based dashboard later |

---

## Other things worth adding

Pieces outside all 15 feature modules that a project running unattended, 24/7, on your own PC genuinely needs:

| Addition | Cost | Why |
|---|---|---|
| **Noise suppression — Picovoice Koala** | 🟡 Freemium, same account as Eagle (100 min/month free) | Cleans mic input before verification/STT — improves accuracy of both |
| **Process supervisor** (`systemd`/Task Scheduler+NSSM, or a Python watchdog loop) | 🟢 Free | Jarvis needs to restart itself if a component crashes at 3am |
| **`tenacity`** | 🟢 Free | Retry/backoff for flaky network calls, separate from the agent-level retry middleware |
| **`pydantic-settings`** | 🟢 Free | Typed config from `.env` — catches a missing API key at startup, not mid-conversation |
| **LangSmith** (tracing) | 🟡 Freemium | See exactly what the agent reasoned and which tools it called — invaluable for debugging unexpected behavior; free tier covers personal use |
| **Docker** | 🟢 Free | Packages the whole stack so a PC reinstall doesn't mean redoing setup |
| **A status indicator** (`pystray` tray icon or overlay) | 🟢 Free | Shows at a glance whether Jarvis is listening/thinking/speaking — matters once verification means it's *not* always listening for everyone |
| **A daily cost/token cap** | 🟢 Free (self-built counter) | A hard stop before a looping bug becomes a surprise bill, on top of the tool-call-limit middleware |

---

## Two ways to build this

**Free-first stack** (get everything running at $0, upgrade piece by piece once you feel a limit):
LangGraph + Ollama (local LLM) + Picovoice free tier + `faster-whisper` local + `edge-tts` + PyAutoGUI + Evolution API + APScheduler/SQLite + Gmail API + ChromaDB + Meta Graph API + `browser-use` + OpenStreetMap + OpenWeatherMap. Real cost: your electricity bill and a decent GPU for the local LLM and Whisper.

**Recommended "pro" stack** (the picks marked ⭐ above): Claude Sonnet 5 as the brain, Picovoice Eagle for the lock, Deepgram for STT, ElevenLabs for TTS, everything else free. At personal-assistant volumes (a few dozen voice commands and messages a day), this realistically runs **$10–30/month** — most of the free tiers above (Picovoice, Deepgram's $200 credit, E2B's $100 credit, OpenWeatherMap, Maps) simply won't be exhausted by one person.

---

## Suggested build order

1. **Core loop first, no voice**: LangGraph + Claude/GPT + a couple of tools (weather, a note-taker) driven by typed input in a terminal. Prove the brain works before adding audio.
2. **Add voice in**: Picovoice Eagle + Cobra (VAD) + Deepgram STT + ElevenLabs TTS, still terminal-based.
3. **Desktop automation**: PyAutoGUI + a vision loop (Claude computer-use or OmniParser). This is the highest-effort module — budget the most time here.
4. **WhatsApp**: Evolution API + FastAPI webhook, Command Mode first, Dictation Mode second (it depends on the voice pipeline from step 2).
5. **Everything else** (email, scheduling, social posting, browser automation, code execution) — these are mostly independent LangGraph tools you can add one at a time without touching the core.

---

## Security & practical notes

- **Never hardcode API keys.** Use a `.env` file with `python-dotenv`, and add `.env` to `.gitignore` from the first commit.
- **Protect your FastAPI webhook.** Anything exposed via ngrok/Cloudflare Tunnel needs its own secret token check on incoming requests — don't rely on the tunnel URL being "hard to guess."
- **Speaker verification isn't foolproof.** Eagle is strong, but for genuinely destructive actions (deleting files, sending money-adjacent messages), consider a second confirmation step even after voice match succeeds.
- **Evolution API + your real number**: keep message volume and timing human-like early on, since the underlying protocol isn't officially sanctioned by WhatsApp.
- **Store voice profiles and any biometric data encrypted at rest** — even for a personal project, since it's literally biometric authentication data.

---

Want me to turn any single module — the LangGraph agent loop, the WhatsApp dictation-mode flow, or the desktop-automation vision loop — into actual starter code and a `requirements.txt` next?
