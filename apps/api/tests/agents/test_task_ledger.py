"""Plan-as-state task ledger — supervisor emits an ordered ``plan``, and
``dispatch_next`` drains it in one turn (P1, specs/agent-task-ledger).

Covers:
- A multi-step ordered plan runs every sub-agent in order, then reflection,
  leaving ``pending_flows == []`` (graph-level, FakeLLM-driven).
- A full ledger (target + ``MAX_LEDGER_STEPS - 1`` follow-ons) completes under
  ``recursion_limit=25`` without ``GraphRecursionError``.
- Supervisor-level ledger normalization: ``booking``, a duplicate of the target
  or an earlier step, and a tier-gated agent are dropped; length is capped at
  ``MAX_LEDGER_STEPS - 1``.
- Backward compatibility: a null/one-item ``plan`` yields the same
  ``pending_flows`` as the legacy ``secondary_agent`` path.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from app.agents.constants import MAX_LEDGER_STEPS
from app.agents.context import AgentContext, resolve_agent_context
from app.agents.graph import build_graph
from app.agents.supervisor import SupervisorIntent, make_supervisor
from app.clients.llm import FakeLLM
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore


def _build(structured_responses, main_responses, fast_responses):
    main = FakeLLM(structured_responses=structured_responses, responses=main_responses)
    fast = FakeLLM(responses=fast_responses)
    return build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )


def _invoke(graph, msg: str, thread_id: str, recursion_limit: int | None = None):
    config: dict = {"configurable": {"thread_id": thread_id}}
    if recursion_limit is not None:
        config["recursion_limit"] = recursion_limit
    return graph.invoke(
        {"messages": [HumanMessage(content=msg)], "user_id": "u1", "trip_id": None},
        config,
    )


def _runtime(ctx: AgentContext) -> SimpleNamespace:
    return SimpleNamespace(context=ctx)


# ---------------------------------------------------------------------------
# (a) Ordered multi-step plan runs in order, then reflection
# ---------------------------------------------------------------------------


def test_ordered_plan_runs_all_steps_in_order():
    graph = _build(
        structured_responses=[
            SupervisorIntent(target_agent="planner", plan=["concierge", "planner"])
        ],
        main_responses=["flights found", "weather is clear", "itinerary drafted"],
        fast_responses=["OK"],
    )
    out = _invoke(graph, "plan my Tokyo weekend: flights, weather, itinerary", "t-a")

    # All three sub-agents ran and the ledger drained.
    assert out["pending_flows"] == []
    assert out["current_flow"] == "planner"  # last step to run

    contents = [m.content for m in out["messages"]]
    for answer in ("flights found", "weather is clear", "itinerary drafted"):
        assert answer in contents
    # Execution order preserved: target first, then each plan step in order.
    assert (
        contents.index("flights found")
        < contents.index("weather is clear")
        < contents.index("itinerary drafted")
    )


# ---------------------------------------------------------------------------
# (b) A full-length ledger fits inside the recursion budget
# ---------------------------------------------------------------------------


def test_full_ledger_completes_within_recursion_limit():
    # target + (MAX_LEDGER_STEPS - 1) follow-ons = MAX_LEDGER_STEPS total runs.
    follow_ons = ["concierge", "journal", "budget"][: MAX_LEDGER_STEPS - 1]
    answers = [f"answer {i}" for i in range(MAX_LEDGER_STEPS)]
    graph = _build(
        structured_responses=[
            SupervisorIntent(target_agent="planner", plan=follow_ons)
        ],
        main_responses=answers,
        fast_responses=["OK"],
    )

    # Must not raise GraphRecursionError at the default limit of 25; reaching
    # this line (invoke returned) is itself the recursion-headroom assertion.
    out = _invoke(graph, "do everything", "t-b", recursion_limit=25)

    # The whole ledger drained, in order, down to the last follow-on.
    assert out["pending_flows"] == []
    assert out["current_flow"] == follow_ons[-1]


# ---------------------------------------------------------------------------
# (c) Supervisor-level ledger normalization: filter + cap
# ---------------------------------------------------------------------------


def _pending_for(intent: SupervisorIntent, ctx: AgentContext) -> list[str]:
    supervisor = make_supervisor(FakeLLM(structured_responses=[intent]))
    cmd = supervisor({"messages": [HumanMessage(content="x")]}, _runtime(ctx))
    return cmd.update["pending_flows"]


def test_plan_allows_repeated_specialist():
    # An ordered plan may legitimately revisit a specialist (planner searches
    # flights first, then builds the itinerary later) — steps are NOT deduped.
    pending = _pending_for(
        SupervisorIntent(target_agent="planner", plan=["concierge", "planner"]),
        AgentContext(),  # permissive (allowed_subagents=None)
    )
    assert pending == ["concierge", "planner"]


def test_plan_cannot_contain_booking_at_type_level():
    # booking can never be a queued follow-on — enforced by the _SecondaryTarget
    # type on the `plan` field, so it never even reaches the Python filter.
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SupervisorIntent(target_agent="planner", plan=["booking"])


def test_plan_step_tier_gated_is_dropped():
    # A step outside allowed_subagents is dropped even when the target passes.
    narrow = replace(
        resolve_agent_context(tier="free"), allowed_subagents=frozenset({"concierge"})
    )
    pending = _pending_for(
        SupervisorIntent(target_agent="concierge", plan=["planner", "budget"]),
        narrow,
    )
    assert pending == []


def test_plan_length_capped_at_max_ledger_steps():
    # A model-emitted plan longer than the cap is truncated in code to the first
    # MAX_LEDGER_STEPS - 1 follow-ons (repeats allowed, so length can exceed it).
    over_long = ["concierge", "planner", "budget", "journal", "concierge"]
    pending = _pending_for(
        SupervisorIntent(target_agent="planner", plan=over_long),
        AgentContext(),
    )
    assert len(pending) == MAX_LEDGER_STEPS - 1
    assert pending == over_long[: MAX_LEDGER_STEPS - 1]


def test_booking_target_queues_no_followons():
    # A booking target routes to HITL with an empty ledger (pre-ledger behavior).
    pending = _pending_for(
        SupervisorIntent(target_agent="booking", plan=["concierge", "budget"]),
        AgentContext(),
    )
    assert pending == []


# ---------------------------------------------------------------------------
# (d) Backward compatibility with the legacy secondary_agent path
# ---------------------------------------------------------------------------


def test_null_plan_falls_back_to_legacy_secondary():
    ctx = AgentContext()
    legacy = _pending_for(
        SupervisorIntent(target_agent="planner", secondary_agent="concierge"), ctx
    )
    one_item_plan = _pending_for(
        SupervisorIntent(target_agent="planner", plan=["concierge"]), ctx
    )
    assert legacy == ["concierge"] == one_item_plan


def test_no_plan_no_secondary_is_empty():
    assert (
        _pending_for(SupervisorIntent(target_agent="concierge"), AgentContext()) == []
    )
