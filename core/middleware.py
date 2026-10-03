"""HumanInTheLoop / Summarization / PII / retry / call-limit middleware.

Every constructor signature here was checked against the installed
langchain.agents.middleware module rather than written from memory.
"""

from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    ModelRetryMiddleware,
    PIIMiddleware,
    SummarizationMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
)

# Every tool capable of a real-world, hard-to-undo action goes here.
# Widen this list as you add more tools in Phase 6 — see the Build
# Workflow's Phase 7: "expand interrupt_on to cover every module."
SENSITIVE_TOOLS = {
    "send_whatsapp_message": True,
    "send_whatsapp_voice_note": True,
    "post_to_instagram": True,
    "post_to_facebook_page": True,
    "send_email": True,
    "write_file": True,
    "apply_patch": True,
    "open_application": True,
}


def build_middleware(model_string: str) -> list:
    """model_string: same model your agent uses — SummarizationMiddleware
    needs its own model reference to write the summary."""
    return [
        SummarizationMiddleware(model=model_string, trigger=("tokens", 4000), keep=("messages", 20)),
        PIIMiddleware("email", strategy="redact", apply_to_input=True),
        HumanInTheLoopMiddleware(interrupt_on=SENSITIVE_TOOLS),
        # run_limit = per message (a runaway-loop guard). thread_limit counted tool calls over the
        # whole life of a saved conversation, so after 25 uses in total Jarvis refused every
        # tool on that WhatsApp/voice thread for good (threads are persisted in data/jarvis.db).
        ToolCallLimitMiddleware(run_limit=25, exit_behavior="continue"),
        ToolRetryMiddleware(max_retries=2),
        ModelRetryMiddleware(max_retries=2),
    ]
