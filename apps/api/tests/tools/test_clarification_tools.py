"""The needs_clarification signal tool."""

from __future__ import annotations

from app.tools.clarification_tools import needs_clarification
from app.tools.registry import ALL_TOOLS, get_tools_for
from langgraph.types import Command


def test_needs_clarification_returns_awaiting_user_command():
    result = needs_clarification.invoke(
        {
            "type": "tool_call",
            "id": "call-clarify-1",
            "name": "needs_clarification",
            "args": {},
        }
    )
    assert isinstance(result, Command)
    assert result.update["awaiting_user"] is True

    messages = result.update["messages"]
    assert len(messages) == 1
    msg = messages[0]
    assert msg.__class__.__name__ == "ToolMessage"
    assert msg.tool_call_id == "call-clarify-1"


def test_needs_clarification_stays_out_of_registry_and_mcp():
    # Control-flow signal, not a domain capability: never in the registry, so never MCP-exposed.
    names = {t.name for t in ALL_TOOLS}
    assert "needs_clarification" not in names
    for domain in ("planner", "concierge", "journal", "booking", "budget"):
        assert "needs_clarification" not in {t.name for t in get_tools_for(domain)}
