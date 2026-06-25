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
