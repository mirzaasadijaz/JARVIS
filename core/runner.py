"""ask_jarvis(): the one safe way for WhatsApp / voice / terminal to talk to the agent.

Calling `agent.invoke(...)` and reading `result["messages"][-1].content` (what the
webhook and the voice loop used to do) breaks in three ways, each of which ended in
an exception or an empty WhatsApp message:

1. Human-in-the-loop pauses.  Sensitive tools (send_whatsapp_message, send_email,
   write_file, ...) are wrapped in HumanInTheLoopMiddleware, which PAUSES the run and
   waits for an approve / edit / reject decision. WhatsApp and the voice loop have no
   way to ask, so the run simply stopped: invoke() returned an empty AIMessage, and the
   paused tool call stayed in the saved conversation. On that thread's NEXT message the
   model was handed a tool call that never got a result - something LLM APIs reject -
   so a single "send a message to Ahmed" request broke that conversation for good.
   Here a pause is answered with a "reject": the model tells the user the action needs
   their confirmation (exactly what the system prompt in core/agent.py asks for) and
   the thread stays healthy. Threads already stuck in that state are healed first.

2. `.content` is not always a string.  Newer Gemini / Claude integrations return a list
   of content blocks. Passing that to WhatsApp, or to text-to-speech, fails.

3. The "last message" is not always a reply (it can be a tool call with no text), and
   an old reply must never be re-sent. Only text produced after the newest user message
   counts.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from langgraph.types import Command

logger = logging.getLogger(__name__)

# How many times in a row a pause may be answered within one message. The model can in
# principle ask for another sensitive tool right after being refused the first.
MAX_APPROVAL_ROUNDS = 3

DEFAULT_DECLINE_MESSAGE = (
    "Not approved: this action can't be confirmed from here. Tell the user in one short "
    "sentence that it needs their explicit confirmation on the Jarvis computer, and do not "
    "retry it."
)

# decide(action_requests) -> one decision dict per request, e.g. {"type": "approve"}
# or {"type": "reject", "message": "..."}.
Decider = Callable[[list], list]


def message_text(content: Any) -> str:
    """Flatten a LangChain message's .content (str, or a list of content blocks) to plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type", "text") == "text" and isinstance(block.get("text"), str):
                parts.append(block["text"])  # skips "thinking" / "tool_use" / image blocks
        return "".join(parts)
    return str(content)


def _final_reply(result: Any) -> str:
    """The agent's text for THIS turn: the newest non-empty AI text after the latest user message."""
    messages = result.get("messages", []) if isinstance(result, dict) else []
    for message in reversed(messages):
        kind = getattr(message, "type", "")
        if kind == "human":
            break
        if kind == "ai":
            text = message_text(message.content).strip()
            if text:
                return text
    return ""


def _action_requests(interrupt: Any) -> list:
    value = getattr(interrupt, "value", None)
    return list(value.get("action_requests", [])) if isinstance(value, dict) else []


def _resume_command(pending: list, decide: Decider) -> Optional[Command]:
    """Builds the Command that answers every pending approval, or None if a pause isn't one we understand."""
    answers = {}
    for interrupt in pending:
        requests = _action_requests(interrupt)
        if not requests:
            return None  # not a human-in-the-loop approval: nothing safe to resume with
        answers[getattr(interrupt, "id", None)] = {"decisions": decide(requests)}
    if len(pending) == 1:
        return Command(resume=next(iter(answers.values())))
    return Command(resume=answers)  # several simultaneous pauses are resumed by interrupt id


def _settle(agent: Any, config: dict, result: Any, decide: Decider) -> Any:
    """Keeps answering approval pauses until the run produces a final answer."""
    for _ in range(MAX_APPROVAL_ROUNDS):
        pending = result.get("__interrupt__") if isinstance(result, dict) else None
        if not pending:
            return result
        command = _resume_command(list(pending), decide)
        if command is None:
            return result
        result = agent.invoke(command, config=config)
    if isinstance(result, dict) and result.get("__interrupt__"):
        logger.warning("Agent is still waiting for approval after %d rounds; the next message will clear it.", MAX_APPROVAL_ROUNDS)
    return result


def ask_jarvis(
    agent: Any,
    text: str,
    thread_id: str,
    *,
    decline_message: str = DEFAULT_DECLINE_MESSAGE,
    on_interrupt: Optional[Decider] = None,
) -> str:
    """Sends `text` to the agent on `thread_id` and returns its reply as plain text ("" if none).

    on_interrupt: optional callback to answer approval requests itself (the terminal
    uses it to ask you y/n). Without one, every sensitive action is declined.
    May raise whatever the agent raises (LLM outage, quota ...): callers decide how to report that.
    """
    config = {"configurable": {"thread_id": thread_id}}

    def decide(requests: list) -> list:
        if on_interrupt is not None:
            return on_interrupt(requests)
        return [{"type": "reject", "message": decline_message} for _ in requests]

    # Heal a conversation that an older version left waiting for an approval nobody could give.
    try:
        stuck = list(getattr(agent.get_state(config), "interrupts", None) or ())
    except Exception:  # no checkpointer / unreadable state: nothing to heal
        stuck = []
    if stuck:
        logger.warning("Thread %s was left waiting for an approval; declining it before continuing.", thread_id)
        _settle(agent, config, {"__interrupt__": stuck}, decide)

    result = agent.invoke({"messages": [{"role": "user", "content": text}]}, config=config)
    result = _settle(agent, config, result, decide)
    return _final_reply(result)
