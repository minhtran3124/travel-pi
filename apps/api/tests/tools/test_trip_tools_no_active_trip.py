"""Regression tests for the absent ``trip_id`` channel (gh-125).

The five trip tools declare ``trip_id`` as a LangGraph-injected arg
(``InjectedState("trip_id")``). When a conversation has no active trip, nothing
ever writes the ``trip_id`` channel, so ``ToolNode`` argument injection looks up
a missing state key and raises ``KeyError: 'trip_id'`` before the tool body ever
runs (``langgraph/prebuilt/tool_node.py`` — a required injected param opts out of
the ``_optional_state_args`` tolerance).

These tests reproduce that crash as a permanent regression and pin the intended
post-fix behaviour from ``specs/gh-125-trip-id-injection-keyerror/design.md``:
invoking any trip tool without an active trip must return an ordinary
``no_active_trip`` guidance ``ToolMessage`` (a plain dict return, wrapped by
``ToolNode``), identical across every sub-agent and NOT routed through
``handle_tool_errors``. They are written TEST-FIRST and are expected to FAIL
(the parametrized case with ``KeyError: 'trip_id'``) until the source fix lands.
"""

from unittest.mock import MagicMock

import pytest
from app.agents.subagents._base import _tool_error_to_message
from langchain_core.messages import AIMessage
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode


class _NoTripState(MessagesState):
    """Minimal graph state mirroring production: ``trip_id`` is declared nullable
    but its channel is never written, so injection must tolerate its absence.

    Inherits ``messages`` from ``MessagesState``.
    """

    user_id: str
    trip_id: str | None


# (tool import name, model-facing args that satisfy the auto-derived schema so
# execution reaches the trip_id-injection step). ``trip_id``/``user_id`` are
# injected, never supplied here.
_TOOL_CASES = [
    ("get_trip_summary", {}),
    ("get_trip_budget", {}),
    ("list_trip_places", {}),
    ("add_place_to_trip", {"place_id": "PLC-0001"}),
    ("add_itinerary_item", {"day": 1, "title": "x"}),
    ("estimate_trip_budget", {}),
    ("set_trip_budget", {"flights": 100}),
]


def _load_tool(name):
    from app.tools import trip_tools

    return getattr(trip_tools, name)


def _no_trip_graph(tool, *, handle_tool_errors):
    """Compile a one-node ToolNode graph over a state whose ``trip_id`` channel
    is never written, giving injection a real LangGraph runtime to resolve from.
    """
    graph = StateGraph(_NoTripState)
    graph.add_node("tools", ToolNode([tool], handle_tool_errors=handle_tool_errors))
    graph.set_entry_point("tools")
    graph.add_edge("tools", END)
    return graph.compile()


def _invoke_no_trip(tool, name, tool_args, *, handle_tool_errors):
    """Drive one tool call through the graph WITHOUT writing ``trip_id`` to state.

    Returns the single ToolMessage produced.
    """
    compiled = _no_trip_graph(tool, handle_tool_errors=handle_tool_errors)
    ai_msg = AIMessage(
        content="",
        tool_calls=[{"name": name, "args": tool_args, "id": "call-1"}],
    )
    result = compiled.invoke({"messages": [ai_msg], "user_id": "test-user-1"})
    tool_msgs = [m for m in result["messages"] if m.__class__.__name__ == "ToolMessage"]
    assert len(tool_msgs) == 1, name
    return tool_msgs[0]


@pytest.mark.parametrize("name, tool_args", _TOOL_CASES)
def test_absent_trip_returns_guidance_not_keyerror(name, tool_args):
    """Case 1: no ``trip_id`` in state -> a ``no_active_trip`` guidance message,
    and NOTHING is raised. Pre-fix this raises ``KeyError: 'trip_id'`` during
    injection (the reproduction promoted to a permanent test).
    """
    tool = _load_tool(name)
    # handle_tool_errors=False so an injection KeyError surfaces as a raised
    # exception rather than being swallowed into an error ToolMessage.
    msg = _invoke_no_trip(tool, name, tool_args, handle_tool_errors=False)
    assert "no_active_trip" in msg.content, name


@pytest.mark.parametrize("name, tool_args", _TOOL_CASES)
def test_absent_trip_guidance_is_handler_independent(name, tool_args):
    """Case 2: even when the ToolNode is given the ``journal``-style
    ``_tool_error_to_message`` handler that relabels failures as a transient
    outage, the guidance is a plain return value (not an error) so the handler
    never runs and its "temporary upstream problem" wording is absent.
    """
    tool = _load_tool(name)
    msg = _invoke_no_trip(
        tool, name, tool_args, handle_tool_errors=_tool_error_to_message
    )
    assert "no_active_trip" in msg.content, name
    assert "temporary upstream problem" not in msg.content, name


@pytest.mark.parametrize("name, tool_args", _TOOL_CASES)
def test_absent_trip_opens_no_db_session(name, tool_args, monkeypatch):
    """Case 3: the absent-trip path returns before any DB work, so
    ``session_scope`` is never entered.
    """
    tool = _load_tool(name)
    fake_scope = MagicMock(name="session_scope")
    monkeypatch.setattr("app.tools.trip_tools.session_scope", fake_scope)
    msg = _invoke_no_trip(tool, name, tool_args, handle_tool_errors=False)
    assert "no_active_trip" in msg.content, name
    fake_scope.assert_not_called()


def test_trip_id_not_in_model_facing_schema():
    """Case 4: giving ``trip_id`` a default (the fix) must NOT expose the
    internal trip UUID to the model — it stays out of ``tool_call_schema``.
    """
    for name, _ in _TOOL_CASES:
        tool = _load_tool(name)
        assert "trip_id" not in tool.tool_call_schema.model_fields, name


def test_mcp_schema_keeps_trip_id_optional():
    """Case 5: pin the MCP contract delta this fix introduced (ESCALATIONS E001).

    ``app/mcp/server.py`` builds each tool's MCP ``inputSchema`` from the raw
    function signature, not from ``tool_call_schema``. Giving ``trip_id`` a
    default therefore moved it out of ``required`` on the served schema — a
    deliberate, backward-compatible relaxation. Assert it, so the change is
    pinned rather than incidental and a future edit cannot flip it unnoticed.
    """
    import asyncio

    from app.mcp.server import build_mcp_server

    served = {t.name: t for t in asyncio.run(build_mcp_server().list_tools())}
    for name, _ in _TOOL_CASES:
        schema = served[name].inputSchema
        assert "trip_id" not in schema.get("required", []), name
        assert "trip_id" in schema["properties"], name
        assert schema["properties"]["trip_id"]["default"] is None, name
