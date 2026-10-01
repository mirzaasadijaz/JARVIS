"""A hard daily spend cap so a looping bug can't quietly rack up a bill.

No LLM provider exposes real-time spend via API, so this estimates cost
from token counts you report after each call, using the per-model rates
from the Tech Stack Guide. Resets automatically at midnight.
"""

import json
import os
from datetime import date

from config import settings

STATE_PATH = "data/cost_tracker.json"

# $ per million tokens, (input, output) — keep in sync with the Tech Stack Guide
RATES = {
    "anthropic:claude-sonnet-5": (2.0, 10.0),
    "anthropic:claude-haiku-4-5": (1.0, 5.0),
    "openai:gpt-5.4": (2.0, 12.0),
    "google_genai:gemini-3-flash": (0.3, 1.5),
    "groq:llama-3.3-70b-versatile": (0.05, 0.10),
}


def _load_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {"date": str(date.today()), "spend_usd": 0.0}
    with open(STATE_PATH) as f:
        state = json.load(f)
    if state["date"] != str(date.today()):
        state = {"date": str(date.today()), "spend_usd": 0.0}
    return state


def _save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_PATH) or ".", exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f)


def record_usage(model_string: str, input_tokens: int, output_tokens: int) -> float:
    """Call after each LLM response. Returns today's running total in USD."""
    state = _load_state()
    input_rate, output_rate = RATES.get(model_string, (0.0, 0.0))
    cost = (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate
    state["spend_usd"] += cost
    _save_state(state)
    return state["spend_usd"]


def check_within_budget() -> None:
    """Raises RuntimeError once today's spend hits DAILY_COST_CAP_USD.
    Call before making an LLM call, not just after."""
    state = _load_state()
    if state["spend_usd"] >= settings.daily_cost_cap_usd:
        raise RuntimeError(
            f"Daily cost cap of ${settings.daily_cost_cap_usd:.2f} reached "
            f"(${state['spend_usd']:.2f} spent today). Raise DAILY_COST_CAP_USD "
            f"in .env if this is expected."
        )
