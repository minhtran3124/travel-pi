"""One failing tool call in a parallel batch must not degrade its siblings."""

from __future__ import annotations

from app.agents.retry import GRACEFUL_MSG, TOOL_FAULT
from app.agents.state import TravelAgentState
from app.agents.subagents._base import _wrapping_tools_node
from app.exceptions import WeatherUnavailableError
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

RAN: list[str] = []


@tool
def make_thing() -> str:
    """Create a thing (side effect)."""
    RAN.append("make_thing")
    return "created"


@tool
def flaky_lookup() -> str:
    """Always fails upstream."""
    RAN.append("flaky_lookup")
    raise WeatherUnavailableError("down")


def _run():
    node = _wrapping_tools_node(
        ToolNode(
            [make_thing, flaky_lookup],
            handle_tool_errors=TOOL_FAULT.handle_tool_errors,
        )
    )
    g = StateGraph(TravelAgentState)
    g.add_node("tools", node)
    g.set_entry_point("tools")
    g.add_edge("tools", END)
    ai = AIMessage(
        content="",
        tool_calls=[
            {"name": "make_thing", "args": {}, "id": "c1"},
            {"name": "flaky_lookup", "args": {}, "id": "c2"},
        ],
    )
    return g.compile().invoke({"messages": [HumanMessage("hi"), ai]})


def test_failing_call_does_not_degrade_siblings():
    RAN.clear()
    out = _run()
    by_id = {m.tool_call_id: m for m in out["messages"] if hasattr(m, "tool_call_id")}
    assert "created" in by_id["c1"].content
    assert by_id["c1"].status != "error"
    assert by_id["c2"].status == "error"
    assert GRACEFUL_MSG in by_id["c2"].content
    # the side-effecting tool ran exactly once
    assert RAN.count("make_thing") == 1
