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
    agent = build_subagent("echoer", [echo], llm, "you echo")
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
    agent = build_subagent("plain", [], llm, "you answer")
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
        result = load_context_node(state)

    # trip_context carries the info
    assert "trip_context" in result
    assert "Tokyo Adventure" in result["trip_context"]
    assert "t1" in result["trip_context"]
    # messages is NOT in result (no trailing SystemMessage injected)
    assert "messages" not in result


def test_load_context_node_no_trip_id_returns_empty():
    """Best-effort: no trip_id -> empty dict, no state mutation."""
    from app.agents.nodes import load_context_node

    assert load_context_node({"messages": [], "trip_id": None}) == {}
    assert load_context_node({"messages": []}) == {}


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

    agent = build_subagent("plain", [], CapturingLLM(responses=["ok"]), "base system")
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


def test_subagent_receives_summary_in_system_prompt():
    """The summary actually reaches the model on a real sub-agent invocation."""
    from app.agents.subagents._base import build_subagent
    from app.clients.llm import FakeLLM

    captured: dict = {}

    class CapturingLLM(FakeLLM):
        def _generate(self, messages, *args, **kwargs):
            captured["messages"] = messages
            return super()._generate(messages, *args, **kwargs)

    agent = build_subagent("plain", [], CapturingLLM(responses=["ok"]), "base system")
    agent.invoke(
        {
            "messages": [HumanMessage(content="and the food?")],
            "summary": "trip to Tokyo; traveller is vegetarian",
        }
    )
    system_msg = captured["messages"][0]
    assert "base system" in system_msg.content
    assert "vegetarian" in system_msg.content
