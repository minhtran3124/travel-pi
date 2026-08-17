"""Ledger early exit — a sub-agent blocked on the traveller abandons the
remaining ``pending_flows`` instead of draining them (MIN-68 / #99).

Wave 1: pure-code unit tests for the ``awaiting_user`` flag.
Wave 2 appends graph-level FakeLLM tests driving the ``needs_clarification`` tool.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.graph import build_graph
from app.agents.nodes import dispatch_next, load_context_node
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

# ---------------------------------------------------------------------------
# dispatch_next: awaiting_user short-circuits the ledger
# ---------------------------------------------------------------------------


def test_dispatch_next_awaiting_user_abandons_queue():
    cmd = dispatch_next(
        {"awaiting_user": True, "pending_flows": ["concierge", "budget"]}
    )
    assert cmd.goto == "reflection"
    assert cmd.update == {"pending_flows": []}


def test_dispatch_next_awaiting_user_with_empty_queue_still_reflects():
    cmd = dispatch_next({"awaiting_user": True, "pending_flows": []})
    assert cmd.goto == "reflection"


def test_dispatch_next_without_flag_drains_normally():
    cmd = dispatch_next({"pending_flows": ["concierge", "budget"]})
    assert cmd.goto == "concierge"
    assert cmd.update["current_flow"] == "concierge"
    assert cmd.update["pending_flows"] == ["budget"]


# ---------------------------------------------------------------------------
# load_context: the flag is single-turn — reset at the start of every turn
# ---------------------------------------------------------------------------


def test_load_context_resets_awaiting_user():
    result = load_context_node(
        {"trip_id": None, "user_id": None}, SimpleNamespace(store=None)
    )
    assert result["awaiting_user"] is False
    assert result["plan_approved"] is False  # existing reset stays intact


# ---------------------------------------------------------------------------
# Graph-level: a blocked sub-agent abandons the ledger (wave 2, MIN-68)
# ---------------------------------------------------------------------------

_CLARIFY_CALL = {
    "content": "",
    "tool_calls": [{"name": "needs_clarification", "args": {}, "id": "call-clarify-1"}],
}


def _build(structured_responses, main_responses, fast_responses):
    main = FakeLLM(structured_responses=structured_responses, responses=main_responses)
    fast = FakeLLM(responses=fast_responses)
    return build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )


def _invoke(graph, msg: str, thread_id: str):
    return graph.invoke(
        {"messages": [HumanMessage(content=msg)], "user_id": "u1", "trip_id": None},
        {"configurable": {"thread_id": thread_id}},
    )


def test_blocked_single_intent_subagent_ends_cleanly():
    # GH-117 Path A: single-intent turns still use the legacy static sub-agent
    # path; a clarification request sets awaiting_user and ends the turn cleanly.
    graph = _build(
        structured_responses=[SupervisorIntent(target_agent="planner")],
        main_responses=[
            _CLARIFY_CALL,
            "Which exact date do you want to depart?",
        ],
        fast_responses=["OK"],
    )
    out = _invoke(graph, "plan a trip at the end of this month", "t-blocked")

    assert out["awaiting_user"] is True
    assert out["current_flow"] == "planner"

    contents = [str(m.content) for m in out["messages"]]
    assert "Which exact date do you want to depart?" in contents


def test_awaiting_user_is_single_turn():
    # Turn 1 blocks on a single-intent clarification; turn 2 (same thread) runs
    # a fresh task list normally.
    graph = _build(
        structured_responses=[
            SupervisorIntent(target_agent="planner"),
            SupervisorIntent(target_agent="planner", plan=["concierge"]),
        ],
        main_responses=[
            _CLARIFY_CALL,
            "Which exact date do you want to depart?",
            "flights found",
            "weather is clear",
            "combined answer",
        ],
        fast_responses=["OK"],
    )
    out1 = _invoke(graph, "plan a trip end of this month", "t-single-turn")
    assert out1["awaiting_user"] is True

    out2 = _invoke(graph, "March 3rd", "t-single-turn")
    assert out2["awaiting_user"] is False
    contents = [str(m.content) for m in out2["messages"]]
    assert "combined answer" in contents


def test_duplicate_clarification_calls_do_not_crash():
    # A zero-arg tool invites duplicate parallel tool calls; two Commands
    # writing awaiting_user in one superstep must not InvalidUpdateError
    # (last-write-wins reducer, MIN-68).
    double_call = {
        "content": "",
        "tool_calls": [
            {"name": "needs_clarification", "args": {}, "id": "call-dup-1"},
            {"name": "needs_clarification", "args": {}, "id": "call-dup-2"},
        ],
    }
    graph = _build(
        structured_responses=[SupervisorIntent(target_agent="planner")],
        main_responses=[
            double_call,
            "Which exact date do you want to depart?",
        ],
        fast_responses=["OK"],
    )
    out = _invoke(graph, "plan a trip end of this month", "t-dup-clarify")

    assert out["awaiting_user"] is True
    contents = [str(m.content) for m in out["messages"]]
    assert "Which exact date do you want to depart?" in contents


def test_blocked_turn_survives_revise_prone_reflection():
    # A clarifying question is by construction "incomplete", so the reflection
    # judge would flag it REVISE and re-run the sub-agent to answer WITHOUT the
    # missing detail. The awaiting_user guard must end the turn regardless, so
    # the question is not revised away (MIN-68 / #99, PR #105 review).
    graph = _build(
        structured_responses=[SupervisorIntent(target_agent="planner")],
        main_responses=[
            _CLARIFY_CALL,
            "Which exact date do you want to depart?",
        ],
        fast_responses=["REVISE"],  # reflection judge would loop if unguarded
    )
    out = _invoke(graph, "plan a trip end of this month", "t-blocked-revise")

    assert out["awaiting_user"] is True
    contents = [str(m.content) for m in out["messages"]]
    assert "Which exact date do you want to depart?" in contents
