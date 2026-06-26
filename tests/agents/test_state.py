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
    # No summary -> base returned unchanged (same object).
    assert system_with_summary({"summary": ""}, base) is base
    assert system_with_summary({}, base) is base
    # Summary present -> one SystemMessage carrying both base + summary.
    combined = system_with_summary({"summary": "traveller is vegetarian"}, base)
    assert isinstance(combined, SystemMessage)
    assert "BASE PROMPT" in combined.content
    assert "vegetarian" in combined.content


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
