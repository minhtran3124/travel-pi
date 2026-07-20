"""State + sub-agent factory (specs/travel-agent Task 5.1)."""

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool


def test_state_has_messages_reducer():
    from app.agents.state import TravelAgentState

    # MessagesState contract: 'messages' key is part of the schema.
    assert "messages" in TravelAgentState.__annotations__


def test_subagent_react_loop_runs_tool():
    from app.agents.subagents._base import build_subagent
    from app.clients.llm import FakeLLM

    @tool
    def echo(text: str) -> str:
        """Echo the text back."""
        return f"echoed: {text}"

    # First turn: call the tool. Second turn: final answer (no tool call).
    llm = FakeLLM(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "echo", "args": {"text": "hi"}, "id": "c1"}],
            ),
            AIMessage(content="done"),
        ]
    )
    agent = build_subagent("echoer", [echo], lambda _: llm, "you echo")
    out = agent.invoke({"messages": [HumanMessage(content="say hi")]})

    contents = [m.content for m in out["messages"]]
    assert "done" in contents
    assert any(
        isinstance(m, ToolMessage) and "echoed: hi" in m.content
        for m in out["messages"]
    )


def test_subagent_without_tools_answers_directly():
    from app.agents.subagents._base import build_subagent
    from app.clients.llm import FakeLLM

    llm = FakeLLM(responses=["a direct answer"])
    agent = build_subagent("plain", [], lambda _: llm, "you answer")
    out = agent.invoke({"messages": [HumanMessage(content="hello")]})
    assert out["messages"][-1].content == "a direct answer"


def test_system_with_summary_folds_summary_into_prompt():
    """REVIEW.md C2: the rolling summary must be re-injected, not silently dropped."""
    from app.agents.state import system_with_summary
    from langchain_core.messages import SystemMessage

    base = SystemMessage(content="BASE PROMPT")
    # No summary, no trip_context -> base returned unchanged (same object).
    assert system_with_summary({"summary": ""}, base) is base
    assert system_with_summary({}, base) is base
    # Summary present -> one SystemMessage carrying both base + summary.
    combined = system_with_summary({"summary": "traveller is vegetarian"}, base)
    assert isinstance(combined, SystemMessage)
    assert "BASE PROMPT" in combined.content
    assert "vegetarian" in combined.content


def test_system_with_summary_folds_trip_context():
    """REVIEW.md M2: trip_context appears in the leading system message."""
    from app.agents.state import system_with_summary
    from langchain_core.messages import SystemMessage

    base = SystemMessage(content="BASE")
    combined = system_with_summary(
        {"trip_context": "Active trip: Rome (city: Rome). Use trip_id=42."}, base
    )
    assert isinstance(combined, SystemMessage)
    assert "BASE" in combined.content
    assert "Rome" in combined.content
    # trip_context absent -> base unchanged
    assert system_with_summary({"trip_context": ""}, base) is base


def test_system_with_summary_folds_both_context_and_summary():
    """Both trip_context and summary end up in one combined system message."""
    from app.agents.state import system_with_summary
    from langchain_core.messages import SystemMessage

    base = SystemMessage(content="BASE")
    combined = system_with_summary(
        {"trip_context": "trip to Paris (id=7)", "summary": "user is vegetarian"},
        base,
    )
    assert "BASE" in combined.content
    assert "Paris" in combined.content
    assert "vegetarian" in combined.content


def test_load_context_node_returns_trip_context_not_messages():
    """REVIEW.md M2: load_context_node must set state field, not append a SystemMessage."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from app.agents.nodes import load_context_node
    from langchain_core.messages import HumanMessage

    detail = MagicMock()
    detail.title = "Tokyo Adventure"
    detail.city = "Tokyo"

    with (
        patch("app.agents.nodes.session_scope") as mock_scope,
        patch("app.agents.nodes.TripService") as mock_svc,
    ):
        mock_scope.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_scope.return_value.__exit__ = MagicMock(return_value=False)
        mock_svc.return_value.get_trip_detail.return_value = detail

        state = {"messages": [HumanMessage(content="plan my trip")], "trip_id": "t1"}
        result = load_context_node(state, SimpleNamespace())

    # trip_context carries the info
    assert "trip_context" in result
    assert "Tokyo Adventure" in result["trip_context"]
    # messages is NOT in result (no trailing SystemMessage injected)
    assert "messages" not in result


def test_load_context_node_no_trip_id_resets_plan_approved():
    """No trip_id -> only the per-turn plan_approved reset, no other mutation.

    load_context runs at the start of every fresh turn and always clears the
    HITL plan-approval flag so outcome="approved" stays scoped to the approving
    turn (issue #63), and likewise clears awaiting_user (MIN-68).
    """
    from types import SimpleNamespace

    from app.agents.nodes import load_context_node

    assert load_context_node({"messages": [], "trip_id": None}, SimpleNamespace()) == {
        "plan_approved": False,
        "awaiting_user": False,
    }
    assert load_context_node({"messages": []}, SimpleNamespace()) == {
        "plan_approved": False,
        "awaiting_user": False,
    }


def test_subagent_receives_trip_context_as_leading_system_message():
    """M2: assembled model call has one leading SystemMessage with trip-context, HumanMessage after."""
    from app.agents.subagents._base import build_subagent
    from app.clients.llm import FakeLLM
    from langchain_core.messages import HumanMessage, SystemMessage

    captured: dict = {}

    class CapturingLLM(FakeLLM):
        def _generate(self, messages, *args, **kwargs):
            captured["messages"] = messages
            return super()._generate(messages, *args, **kwargs)

    capturing = CapturingLLM(responses=["ok"])
    agent = build_subagent("plain", [], lambda _: capturing, "base system")
    agent.invoke(
        {
            "messages": [HumanMessage(content="where to eat?")],
            "trip_context": "Active trip: Tokyo Adventure (city: Tokyo). Use trip_id=99.",
        }
    )
    msgs = captured["messages"]
    # First message is the only SystemMessage and contains trip context
    assert isinstance(msgs[0], SystemMessage)
    assert "base system" in msgs[0].content
    assert "Tokyo Adventure" in msgs[0].content
    # Human message is next
    assert isinstance(msgs[1], HumanMessage)
    # No trailing or mid-conversation SystemMessages
    system_count = sum(1 for m in msgs if isinstance(m, SystemMessage))
    assert system_count == 1


def test_ground_current_date_injects_today():
    """ground_current_date grounds a real date and forbids inventing one."""
    from datetime import datetime, timezone

    from app.agents.state import ground_current_date
    from langchain_core.messages import SystemMessage

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    grounded = ground_current_date(SystemMessage(content="BASE PROMPT"))
    assert isinstance(grounded, SystemMessage)
    assert "BASE PROMPT" in grounded.content
    assert today in grounded.content
    assert "resolve_date" in grounded.content
    # No date given is the one case that must still produce a question: the note has to
    # forbid the fallback explicitly, not merely permit asking. A live probe showed the
    # model defaulting to today when the note only said "ask only when…".
    assert "must ask" in grounded.content.lower()
    assert f"never fall back to {today}" in grounded.content.lower()


def test_subagent_receives_todays_date_in_system_prompt():
    """The current date reaches the model so it can resolve 'today' instead of guessing."""
    from datetime import datetime, timezone

    from app.agents.subagents._base import build_subagent
    from app.clients.llm import FakeLLM

    captured: dict = {}

    class CapturingLLM(FakeLLM):
        def _generate(self, messages, *args, **kwargs):
            captured["messages"] = messages
            return super()._generate(messages, *args, **kwargs)

    capturing = CapturingLLM(responses=["ok"])
    agent = build_subagent("plain", [], lambda _: capturing, "base system")
    agent.invoke({"messages": [HumanMessage(content="find me a flight today")]})

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    system_msg = captured["messages"][0]
    assert today in system_msg.content
    assert "base system" in system_msg.content


def test_subagent_receives_summary_in_system_prompt():
    """The summary actually reaches the model on a real sub-agent invocation."""
    from app.agents.subagents._base import build_subagent
    from app.clients.llm import FakeLLM

    captured: dict = {}

    class CapturingLLM(FakeLLM):
        def _generate(self, messages, *args, **kwargs):
            captured["messages"] = messages
            return super()._generate(messages, *args, **kwargs)

    capturing = CapturingLLM(responses=["ok"])
    agent = build_subagent("plain", [], lambda _: capturing, "base system")
    agent.invoke(
        {
            "messages": [HumanMessage(content="and the food?")],
            "summary": "trip to Tokyo; traveller is vegetarian",
        }
    )
    system_msg = captured["messages"][0]
    assert "base system" in system_msg.content
    assert "vegetarian" in system_msg.content


def test_ground_current_date_uses_timezone():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from app.agents.state import ground_current_date
    from langchain_core.messages import SystemMessage

    tz = "Asia/Ho_Chi_Minh"
    today_local = datetime.now(ZoneInfo(tz)).strftime("%Y-%m-%d")
    grounded = ground_current_date(SystemMessage(content="BASE"), tz)
    assert today_local in grounded.content
    assert tz in grounded.content
    assert "BASE" in grounded.content


def test_ground_current_date_invalid_tz_falls_back_to_utc():
    from app.agents.state import ground_current_date
    from langchain_core.messages import SystemMessage

    grounded = ground_current_date(SystemMessage(content="BASE"), "Not/AZone")
    assert "UTC" in grounded.content  # fell back, did not raise
