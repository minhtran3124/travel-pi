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
    "tool_calls": [
        {"name": "needs_clarification", "args": {}, "id": "call-clarify-1"}
    ],
}


def _build(structured_responses, main_responses, fast_responses):
    main = FakeLLM(
        structured_responses=structured_responses, responses=main_responses
    )
    fast = FakeLLM(responses=fast_responses)
    return build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )


def _invoke(graph, msg: str, thread_id: str):
    return graph.invoke(
        {"messages": [HumanMessage(content=msg)], "user_id": "u1", "trip_id": None},
        {"configurable": {"thread_id": thread_id}},
    )


def test_blocked_subagent_abandons_queued_steps():
    # Both queued follow-ons are main-tier agents (budget/journal are
    # FAST_AGENTS and would consume fast_responses, making a sentinel there
    # dead scripting) — so a regression would surface a NEVER-RUN sentinel.
    graph = _build(
        structured_responses=[
            SupervisorIntent(target_agent="planner", plan=["concierge", "planner"])
        ],
        main_responses=[
            _CLARIFY_CALL,
            "Which exact date do you want to depart?",
            "NEVER-RUN concierge answer",
            "NEVER-RUN planner follow-on answer",
        ],
        fast_responses=["OK"],
    )
    out = _invoke(graph, "plan a trip at the end of this month", "t-blocked")

    assert out["awaiting_user"] is True
    assert out["pending_flows"] == []
    assert out["current_flow"] == "planner"  # queued steps never ran

    contents = [str(m.content) for m in out["messages"]]
    assert "Which exact date do you want to depart?" in contents
    assert not any("NEVER-RUN" in c for c in contents)


def test_awaiting_user_is_single_turn():
    # Turn 1 blocks; turn 2 (same thread) must drain a fresh ledger normally.
    graph = _build(
        structured_responses=[
            SupervisorIntent(target_agent="planner", plan=["concierge"]),
            SupervisorIntent(target_agent="planner", plan=["concierge"]),
        ],
        main_responses=[
            _CLARIFY_CALL,
            "Which exact date do you want to depart?",
            "flights found",
            "weather is clear",
        ],
        fast_responses=["OK"],
    )
    out1 = _invoke(graph, "plan a trip end of this month", "t-single-turn")
    assert out1["awaiting_user"] is True

    out2 = _invoke(graph, "March 3rd", "t-single-turn")
    assert out2["awaiting_user"] is False
    contents = [str(m.content) for m in out2["messages"]]
    assert "flights found" in contents
    assert "weather is clear" in contents  # fresh ledger drained
