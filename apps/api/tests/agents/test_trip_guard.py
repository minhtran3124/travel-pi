"""Trip guard — no active trip blocks trip-scoped tools deterministically (#113).

The first round of #113 only *described* the failure to the model ("ask the
traveller which trip"), leaving the outcome to whether the model obeys prose — a
model that ignores it could call the same tool again forever (PR #116 review).
These tests pin the deterministic behavior: the tool never runs, `awaiting_user`
is set exactly as `needs_clarification` sets it, and nothing claims an outage.

Offline: FakeLLM only, no network.
"""

from __future__ import annotations

import logging
from typing import Annotated

from app.agents.constants import NO_ACTIVE_TRIP_MSG
from app.agents.subagents._base import (
    _make_trip_guard,
    _tools_needing_trip,
    build_subagent,
)
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from app.core.config import get_settings
from app.tools.registry import get_tools_for
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool as tool_decorator
from langgraph.prebuilt import InjectedState

_BUDGET_CALL = {
    "content": "",
    "tool_calls": [{"name": "get_trip_budget", "args": {}, "id": "call-budget-1"}],
}


def _ai_with_calls(*names: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": n, "args": {}, "id": f"call-{i}"} for i, n in enumerate(names)
        ],
    )


# ---------------------------------------------------------------------------
# Which tools need a trip — derived, not hardcoded
# ---------------------------------------------------------------------------


def test_detects_injected_trip_id_tools():
    needing = _tools_needing_trip(get_tools_for("planner"))

    assert "get_trip_budget" in needing
    assert "get_trip_summary" in needing
    assert "list_trip_places" in needing
    # create_trip takes no trip_id — it is how a traveller gets one.
    assert "create_trip" not in needing
    # A tool whose trip_id the model supplies itself is not state-scoped.
    assert "search_flights" not in needing


def test_budget_agent_guards_new_budget_tools():
    """The budget agent's guard covers estimate_trip_budget / set_trip_budget
    (specs/agent-budget-trip-context SC-5) — the agent path, not only ToolNode."""
    needing = _tools_needing_trip(get_tools_for("budget"))

    assert "estimate_trip_budget" in needing
    assert "set_trip_budget" in needing


# ---------------------------------------------------------------------------
# Pass-through cases
# ---------------------------------------------------------------------------


def test_guard_passes_through_when_a_trip_is_active():
    guard = _make_trip_guard(frozenset({"get_trip_budget"}))
    cmd = guard({"trip_id": "t-1", "messages": [_ai_with_calls("get_trip_budget")]})

    assert cmd.goto == "tools"
    assert not cmd.update


def test_guard_passes_through_when_no_call_needs_a_trip():
    guard = _make_trip_guard(frozenset({"get_trip_budget"}))
    cmd = guard({"trip_id": None, "messages": [_ai_with_calls("search_flights")]})

    assert cmd.goto == "tools"


# ---------------------------------------------------------------------------
# The blocking case
# ---------------------------------------------------------------------------


def test_guard_blocks_and_sets_awaiting_user():
    guard = _make_trip_guard(frozenset({"get_trip_budget"}))
    cmd = guard({"trip_id": None, "messages": [_ai_with_calls("get_trip_budget")]})

    assert cmd.goto == "assistant", "must not reach the tools node"
    assert cmd.update["awaiting_user"] is True
    (msg,) = cmd.update["messages"]
    assert isinstance(msg, ToolMessage)
    assert msg.tool_call_id == "call-0"
    assert msg.status == "error"
    assert msg.content == NO_ACTIVE_TRIP_MSG


def test_blocked_message_never_claims_an_outage_and_never_asks_for_an_id():
    """The traveller has never seen a trip id, so asking for one is a dead end."""
    assert "NOT an outage" in NO_ACTIVE_TRIP_MSG
    assert "retrying will fail identically" in NO_ACTIVE_TRIP_MSG
    assert "never by id" in NO_ACTIVE_TRIP_MSG
    assert "destination and rough dates" in NO_ACTIVE_TRIP_MSG
    assert "try again shortly" not in NO_ACTIVE_TRIP_MSG


def test_every_pending_call_gets_a_paired_tool_message():
    """An unpaired tool call makes the provider reject the next assistant turn."""
    guard = _make_trip_guard(frozenset({"get_trip_budget"}))
    cmd = guard(
        {
            "trip_id": None,
            "messages": [_ai_with_calls("get_trip_budget", "search_flights")],
        }
    )

    ids = [m.tool_call_id for m in cmd.update["messages"]]
    assert ids == ["call-0", "call-1"], "both calls must be answered"
    contents = {m.tool_call_id: m.content for m in cmd.update["messages"]}
    assert contents["call-0"] == NO_ACTIVE_TRIP_MSG
    assert "blocked on the traveller" in contents["call-1"]


# ---------------------------------------------------------------------------
# End-to-end through the real graph (the review asked for this)
# ---------------------------------------------------------------------------


def test_graph_turn_with_no_trip_blocks_the_tool_and_awaits_the_traveller(tmp_path):
    from app.agents.graph import build_graph
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.store.memory import InMemoryStore

    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent="planner")],
        responses=[
            _BUDGET_CALL,  # model reaches for a trip-scoped tool...
            "Which trip do you mean — Tokyo in August, or another one?",
        ],
    )
    graph = build_graph(
        llm=main,
        fast_llm=FakeLLM(responses=["OK"]),
        checkpointer=MemorySaver(),
        store=InMemoryStore(),
    )

    out = graph.invoke(
        {
            "messages": [HumanMessage(content="How much have I spent so far?")],
            "user_id": "u1",
            "trip_id": None,
        },
        {"configurable": {"thread_id": "t-no-trip"}},
    )

    assert out["awaiting_user"] is True, "the turn must be blocked on the traveller"

    tool_msgs = [m for m in out["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_msgs) == 1, "exactly the blocked call, answered once"
    assert tool_msgs[0].content == NO_ACTIVE_TRIP_MSG
    # The tool never executed: every ToolMessage came from the guard, so none
    # carries a successful result. (A real get_trip_budget run would 404 on a
    # None trip_id and surface status="error" with a different body.)
    assert all(m.status == "error" for m in tool_msgs)
    assert not any(
        "budget" in str(m.content).lower() and "cap" in str(m.content).lower()
        for m in tool_msgs
    )
    joined = " ".join(str(m.content) for m in out["messages"])
    assert "try again shortly" not in joined, "must never read as an outage"


# ---------------------------------------------------------------------------
# Routing: the guard is only visited when it can actually block (SC-1, SC-3)
# ---------------------------------------------------------------------------


def test_trip_scoped_call_skips_guard_when_trip_active():
    """SC-1: with an active trip, `assistant` routes straight to `tools` — the
    compiled subgraph never visits `trip_guard` for that round."""

    @tool_decorator
    def trip_scoped_tool(
        trip_id: Annotated[str | None, InjectedState("trip_id")] = None,
    ) -> str:
        """A trip-scoped tool used only to exercise routing."""
        return "ok"

    llm = FakeLLM(
        responses=[
            {"tool_calls": [{"name": "trip_scoped_tool", "args": {}, "id": "call-0"}]},
            "done",
        ]
    )
    agent = build_subagent("test_agent", [trip_scoped_tool], lambda _: llm, "you test")

    node_keys: set[str] = set()
    for chunk in agent.stream(
        {"messages": [HumanMessage(content="go")], "trip_id": "t-1"},
        stream_mode="updates",
    ):
        node_keys.update(chunk.keys())

    assert "trip_guard" not in node_keys, "guard must be skipped with an active trip"
    assert "tools" in node_keys


def test_sequential_ten_round_budget_fits_recursion_limit():
    """SC-3: 10 sequential trip-scoped tool rounds complete under the unchanged
    ``agent_recursion_limit`` (25).

    Old topology (assistant, trip_guard, tools per round): 3*10+1 = 31 super-steps
    — over budget. New topology (assistant, tools per round, guard skipped when a
    trip is active): 2*10+1 = 21 <= 25.
    """

    @tool_decorator
    def trip_scoped_tool(
        trip_id: Annotated[str | None, InjectedState("trip_id")] = None,
    ) -> str:
        """A trip-scoped tool used only to exercise the round budget."""
        return "ok"

    responses: list[dict | str] = [
        {"tool_calls": [{"name": "trip_scoped_tool", "args": {}, "id": f"call-{i}"}]}
        for i in range(10)
    ]
    responses.append("all done")
    llm = FakeLLM(responses=responses)
    agent = build_subagent("test_agent", [trip_scoped_tool], lambda _: llm, "you test")

    limit = get_settings().agent_recursion_limit
    out = agent.invoke(
        {"messages": [HumanMessage(content="go")], "trip_id": "t-1"},
        {"recursion_limit": limit},
    )

    final = out["messages"][-1]
    assert isinstance(final, AIMessage) and not getattr(final, "tool_calls", None)
    assert final.content == "all done"


# ---------------------------------------------------------------------------
# Fail-open is allowed; failing open SILENTLY is not
# ---------------------------------------------------------------------------


def _budget_tool():
    return next(t for t in get_tools_for("budget") if t.name == "get_trip_budget")


def test_unreadable_annotations_are_warned_not_swallowed(caplog):
    """A wrapped tool drops out of the guard — that must be visible in the logs.

    Found the hard way: a UAT probe wrapped `tool.func` to count executions, which
    stripped the annotations `_tools_needing_trip` reads. The guard silently
    stopped covering `get_trip_budget` and the UAT produced a convincing false
    failure. Nothing in the logs said the guard had been disabled.
    """
    tool = _budget_tool()
    assert tool.name in _tools_needing_trip([tool])  # readable to begin with

    original = tool.func
    try:
        tool.func = lambda **kw: original(**kw)  # a wrapper, annotations gone
        with caplog.at_level(logging.WARNING, logger="app.agents.subagents._base"):
            needing = _tools_needing_trip([tool])
    finally:
        tool.func = original

    assert tool.name not in needing, "precondition: the wrapper defeats detection"
    assert "cannot read annotations" in caplog.text
    assert tool.name in caplog.text


def test_no_warning_for_a_tool_that_simply_has_no_trip_id(caplog):
    """The warning must not cry wolf on legitimately non-trip-scoped tools."""
    tools = [t for t in get_tools_for("planner") if t.name == "create_trip"]
    assert tools, "fixture assumption: planner binds create_trip"

    with caplog.at_level(logging.WARNING, logger="app.agents.subagents._base"):
        assert not _tools_needing_trip(tools)

    assert "cannot read annotations" not in caplog.text


def test_every_registered_tool_is_introspectable():
    """The invariant that makes "no hints at all" a safe alarm.

    `_tools_needing_trip` treats zero readable hints as "annotations were
    stripped" and warns. That is only free of false positives while every real
    tool has some. If a future tool legitimately has none, this fails here rather
    than by crying wolf on every graph build.
    """
    import typing

    for agent in ("planner", "concierge", "journal", "booking", "budget"):
        for tool in get_tools_for(agent):
            fn = tool.coroutine or tool.func
            hints = typing.get_type_hints(fn, include_extras=True)
            assert hints, f"{agent}/{tool.name} has no readable type hints"
