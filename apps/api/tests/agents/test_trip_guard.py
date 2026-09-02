"""Trip guard — no active trip blocks trip-scoped tools deterministically (#113).

The first round of #113 only *described* the failure to the model ("ask the
traveller which trip"), leaving the outcome to whether the model obeys prose — a
model that ignores it could call the same tool again forever (PR #116 review).
These tests pin the deterministic behavior: the tool never runs, `awaiting_user`
is set exactly as `needs_clarification` sets it, and nothing claims an outage.

Offline: FakeLLM only, no network.
"""

from __future__ import annotations

from app.agents.constants import NO_ACTIVE_TRIP_MSG
from app.agents.subagents._base import _make_trip_guard, _tools_needing_trip
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from app.tools.registry import get_tools_for
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

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
