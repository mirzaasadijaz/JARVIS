"""create_agent(): picks the model, registers every tool, wires in the
full middleware stack. This is the Phase 8 "final" version — it
supersedes the Phase 1 agent.py, which only had the weather tool.
"""

import sys
from pathlib import Path

# Only matters if this file is ever run directly (`python core/agent.py`)
# rather than via run_voice.py/run_server.py, which live at the project
# root and don't need this.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain.agents import create_agent
from langgraph.checkpoint.sqlite import SqliteSaver

from config import settings
from core.middleware import build_middleware
from tools.browser import browser_click, browser_get_html, browser_get_text, browser_navigate, browser_type
from tools.coding import apply_patch, read_file, write_file
from tools.desktop import click_at, open_application, press_key, read_clipboard, take_screenshot, type_text, write_clipboard
from tools.documents import ingest_local_file, search_documents
from tools.gmail import search_inbox, send_email
from tools.maps import geocode, get_directions
from tools.memory import save_note, search_notes
from tools.research import search_wikipedia, web_search
from tools.scheduling import cancel_reminder, list_reminders, schedule_reminder, scheduler, set_alarm
from tools.social import post_to_facebook_page, post_to_instagram
from tools.weather import get_forecast, get_weather
from tools.whatsapp import send_whatsapp_message, send_whatsapp_voice_note

SYSTEM_PROMPT = """You are Jarvis, a personal AI assistant for Asad. Be
concise and direct. Use tools rather than guessing whenever a question
needs current information or a real-world action. Some tools require
explicit human approval before they run — if one is declined, don't
retry it silently; tell Asad it needs his confirmation."""

_MODEL_STRINGS = {
    "anthropic": "anthropic:claude-sonnet-5",
    "openai": "openai:gpt-5.4",
    "google": "google_genai:gemini-3.8-flash",
    "groq": "groq:llama-3.3-70b-versatile",
}

ALL_TOOLS = [
    # weather (Phase 1)
    get_weather, get_forecast,
    # desktop (Phase 4)
    take_screenshot, click_at, type_text, press_key, open_application, read_clipboard, write_clipboard,
    # whatsapp (Phase 5)
    send_whatsapp_message, send_whatsapp_voice_note,
    # scheduling, memory, email, social, research, maps (Phase 6)
    set_alarm, schedule_reminder, list_reminders, cancel_reminder,
    save_note, search_notes,
    send_email, search_inbox,
    post_to_instagram, post_to_facebook_page,
    search_wikipedia, web_search,
    geocode, get_directions,
    # browser automation (Phase 6)
    browser_navigate, browser_click, browser_type, browser_get_text, browser_get_html,
    # coding tool (Phase 6)
    read_file, write_file, apply_patch,
    # RAG over files from WhatsApp and computer (new)
    ingest_local_file, search_documents,
]

provider, _ = settings.active_brain
model_string = _MODEL_STRINGS[provider]

# SqliteSaver persists conversation state across restarts (Phase 7 upgrade
# from Phase 1's InMemorySaver). Requires: pip install langgraph-checkpoint-sqlite
_checkpointer_cm = SqliteSaver.from_conn_string("data/jarvis.db")
checkpointer = _checkpointer_cm.__enter__()

agent = create_agent(
    model=model_string,
    tools=ALL_TOOLS,
    system_prompt=SYSTEM_PROMPT,
    middleware=build_middleware(model_string),
    checkpointer=checkpointer,
)

# tools/scheduling.py's alarms need the scheduler actually running.
scheduler.start()


if __name__ == "__main__":
    thread_id = "terminal-test"
    print(f"Jarvis (brain: {provider}, {len(ALL_TOOLS)} tools). Type 'quit' to exit.\n")
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in {"quit", "exit"}:
            break
        if not user_input:
            continue
        result = agent.invoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config={"configurable": {"thread_id": thread_id}},
        )
        print(f"Jarvis: {result['messages'][-1].content}\n")
