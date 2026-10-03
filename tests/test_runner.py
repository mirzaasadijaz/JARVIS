"""core.runner.ask_jarvis against a REAL LangGraph agent with the human-in-the-loop middleware."""

from langchain_core.messages import AIMessage

from core.runner import ask_jarvis, message_text

SENSITIVE = AIMessage(
    content="",
    tool_calls=[{"name": "send_whatsapp_message", "args": {"to": "92300", "message": "hi"}, "id": "call_1"}],
)


def test_plain_answer(make_agent):
    agent, _ = make_agent([AIMessage(content="Hello!")])
    assert ask_jarvis(agent, "hi", "t") == "Hello!"


def test_message_text_flattens_content_blocks():
    assert message_text("plain") == "plain"
    assert message_text(None) == ""
    blocks = [
        {"type": "thinking", "thinking": "hmm"},
        {"type": "text", "text": "Hello ", "extras": {"signature": "abc"}},
        {"type": "text", "text": "there"},
        {"type": "tool_use", "name": "x"},
    ]
    assert message_text(blocks) == "Hello there"
    assert message_text(["a", {"type": "text", "text": "b"}]) == "ab"


def test_list_content_reply_comes_back_as_text(make_agent):
    agent, _ = make_agent([AIMessage(content=[{"type": "text", "text": "From blocks"}])])
    assert ask_jarvis(agent, "hi", "t") == "From blocks"


def test_sensitive_tool_is_declined_and_the_model_explains(make_agent):
    agent, model = make_agent([SENSITIVE, AIMessage(content="That needs your confirmation on the PC.")])
    reply = ask_jarvis(agent, "send hi to 92300", "t")
    assert reply == "That needs your confirmation on the PC."  # not "" (the old empty WhatsApp message)
    # the tool was NOT executed: the model was told it was declined
    shown = [m.content for m in model.seen[-1] if m.type == "tool"]
    assert shown and "rejected" in shown[0].lower()


def test_conversation_stays_healthy_after_a_declined_action(make_agent):
    """The old behaviour: the NEXT message on the thread was handed a tool call with no result."""
    agent, model = make_agent([SENSITIVE, AIMessage(content="Needs confirmation."), AIMessage(content="Yes, I'm here.")])
    ask_jarvis(agent, "send hi to 92300", "t")
    assert ask_jarvis(agent, "are you there?", "t") == "Yes, I'm here."
    history = model.seen[-1]
    call_ids = [c["id"] for m in history if m.type == "ai" for c in m.tool_calls]
    result_ids = [m.tool_call_id for m in history if m.type == "tool"]
    assert call_ids and call_ids == result_ids, "every tool call must have a result"


def test_a_thread_already_stuck_by_an_older_version_is_healed(make_agent):
    agent, model = make_agent([SENSITIVE, AIMessage(content="Needs confirmation."), AIMessage(content="Back to normal.")])
    cfg = {"configurable": {"thread_id": "legacy"}}
    agent.invoke({"messages": [{"role": "user", "content": "send hi"}]}, cfg)  # what the old webhook did, then stopped
    assert agent.get_state(cfg).interrupts, "precondition: the thread is stuck waiting for approval"
    assert ask_jarvis(agent, "hello?", "legacy") == "Back to normal."
    assert not agent.get_state(cfg).interrupts


def test_terminal_callback_can_approve(make_agent):
    agent, _ = make_agent([SENSITIVE, AIMessage(content="Sent it.")])
    seen = []

    def approve(requests):
        seen.extend(r["name"] for r in requests)
        return [{"type": "approve"} for _ in requests]

    assert ask_jarvis(agent, "send hi", "t", on_interrupt=approve) == "Sent it."
    assert seen == ["send_whatsapp_message"]


def test_never_resends_an_old_reply_when_this_turn_has_no_text(make_agent):
    agent, _ = make_agent([AIMessage(content="First answer."), AIMessage(content="")])
    assert ask_jarvis(agent, "one", "t") == "First answer."
    assert ask_jarvis(agent, "two", "t") == ""  # empty, NOT "First answer." again


def test_agent_errors_propagate_to_the_caller(make_agent):
    agent, _ = make_agent([RuntimeError("quota exceeded")])
    try:
        ask_jarvis(agent, "hi", "t")
    except Exception as exc:
        assert "quota exceeded" in str(exc)
    else:
        raise AssertionError("expected the LLM error to propagate")


# ---------------------------------------------------------------------------------------------
# core/middleware.py — the tool-call cap must be per message, not per saved conversation
# ---------------------------------------------------------------------------------------------


def test_tool_call_cap_is_per_message_so_long_lived_threads_keep_working():
    import sqlite3

    from langchain.agents import create_agent
    from langchain.agents.middleware import ToolCallLimitMiddleware

    from conftest import ScriptedModel, get_time
    from core.middleware import build_middleware
    from langgraph.checkpoint.sqlite import SqliteSaver

    turns = 30  # more than the cap of 25: the old thread_limit would have refused the last five
    script = []
    for i in range(turns):
        script += [AIMessage(content="", tool_calls=[{"name": "get_time", "args": {}, "id": f"c{i}"}]), AIMessage(content=f"done {i}")]
    model = ScriptedModel(script=script, seen=[])

    stack = build_middleware(model)  # build_middleware only passes the "model string" on to SummarizationMiddleware
    limiter = next(m for m in stack if isinstance(m, ToolCallLimitMiddleware))
    assert limiter.thread_limit is None and limiter.run_limit == 25

    agent = create_agent(model=model, tools=[get_time], middleware=stack, checkpointer=SqliteSaver(sqlite3.connect(":memory:", check_same_thread=False)))
    cfg = {"configurable": {"thread_id": "whatsapp-long-lived"}}
    for i in range(turns):
        reply = ask_jarvis(agent, f"message {i}", "whatsapp-long-lived")
        assert reply == f"done {i}"
    tool_results = [m.content for m in agent.get_state(cfg).values["messages"] if m.type == "tool"]
    assert len(tool_results) == turns and all(r == "12:00" for r in tool_results), "no tool call may have been refused"
