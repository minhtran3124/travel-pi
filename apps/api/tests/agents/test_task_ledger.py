"""Plan-as-state task ledger — supervisor emits an ordered ``plan``, and
``dispatch_next`` drains it in one turn (P1, specs/agent-task-ledger).

Covers:
- A multi-step ordered plan runs every sub-agent in order, then reflection,
  leaving ``pending_flows == []`` (graph-level, FakeLLM-driven).
- A full ledger (target + ``MAX_LEDGER_STEPS - 1`` follow-ons) completes under
  ``recursion_limit=25`` without ``GraphRecursionError``.
- Supervisor-level task-list normalization: ``booking``, a duplicate of the
  target or an earlier step, and a tier-gated agent are dropped; the follow-on
  count is capped at ``MAX_LEDGER_STEPS - 1``.
- A one-item ``plan`` yields the target plus the single follow-on task agent.

Wave 1 (specs/multi-intent-single-path): the supervisor emits a DEDUPLICATED
``tasks`` list and no longer writes ``pending_flows``; these tests read the task
agents from ``cmd.update["tasks"]``.
"""

from __future__ import annotations

import asyncio
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


def _drive(graph, *args, **kwargs):
    """Run the graph the way production does — asynchronously.

    ``synthesis_worker`` is an async node (#178: the specialists bind async-only
    tools), and a sync ``graph.invoke`` cannot execute one. Production always uses
    ``ainvoke``/``astream``, so driving the graph this way is also the more
    faithful test.
    """
    return asyncio.run(graph.ainvoke(*args, **kwargs))


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
    return _drive(
        graph,
        {"messages": [HumanMessage(content=msg)], "user_id": "u1", "trip_id": None},
        config,
    )


def _runtime(ctx: AgentContext) -> SimpleNamespace:
    return SimpleNamespace(context=ctx)


# ---------------------------------------------------------------------------
# (a) Ordered multi-step plan runs in order, then reflection
# ---------------------------------------------------------------------------


def test_ordered_plan_runs_all_steps_in_parallel_then_synthesizes():
    # GH-117 Path A: a multi-step plan is dispatched to parallel synthesis
    # workers; the synthesizer combines all findings into one answer. The
    # repeated planner in the plan is deduped, so exactly two distinct workers
    # run (planner + concierge).
    graph = _build(
        structured_responses=[
            SupervisorIntent(target_agent="planner", plan=["concierge", "planner"])
        ],
        main_responses=[
            "flights found",
            "weather is clear",
            "combined answer",
        ],
        fast_responses=["OK"],
    )
    out = _invoke(graph, "plan my Tokyo weekend: flights, weather, itinerary", "t-a")

    # Both distinct specialist tasks ran and produced results.
    agents = {r["agent"] for r in out.get("task_results", [])}
    assert agents == {"planner", "concierge"}

    # The graph ended after synthesis.
    assert out["current_flow"] == "synthesize"

    # The synthesized answer appears in the final messages.
    contents = [m.content for m in out["messages"]]
    assert "combined answer" in contents


# ---------------------------------------------------------------------------
# (b) A full-length ledger fits inside the recursion budget
# ---------------------------------------------------------------------------


def test_full_task_list_completes_within_recursion_limit():
    # GH-117 Path A: target + (MAX_LEDGER_STEPS - 1) follow-ons run as parallel
    # workers, then synthesize + reflection. The full graph must still complete
    # under the default recursion limit.
    follow_ons = ["concierge", "journal", "budget"][: MAX_LEDGER_STEPS - 1]
    worker_count = 1 + len(follow_ons)
    answers = [f"answer {i}" for i in range(worker_count)] + ["combined answer"]
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

    # Every worker produced a result and the graph ended at synthesis.
    assert len(out.get("task_results", [])) == worker_count
    assert out["current_flow"] == "synthesize"


# ---------------------------------------------------------------------------
# (c) Supervisor-level ledger normalization: filter + cap
# ---------------------------------------------------------------------------


def _task_agents_for(intent: SupervisorIntent, ctx: AgentContext) -> list[str]:
    supervisor = make_supervisor(FakeLLM(structured_responses=[intent]))
    cmd = supervisor({"messages": [HumanMessage(content="x")]}, _runtime(ctx))
    # Wave 1: the supervisor no longer writes the sequential ledger.
    assert "pending_flows" not in cmd.update
    return [t["agent"] for t in cmd.update.get("tasks", [])]


def test_plan_dedupes_repeated_specialist():
    # Each worker is dispatched in parallel and sees only this message, so a
    # repeated specialist would just redo the same work — steps ARE deduped
    # (primary first, then each new follow-on once).
    agents = _task_agents_for(
        SupervisorIntent(target_agent="planner", plan=["concierge", "planner"]),
        AgentContext(),  # permissive (allowed_subagents=None)
    )
    assert agents == ["planner", "concierge"]  # planner not duplicated


def test_plan_cannot_contain_booking_at_type_level():
    # booking can never be a queued follow-on. Since GH-180 the `plan` validator
    # DROPS it instead of raising, so a malformed routing decision degrades to
    # the primary intent rather than killing the whole turn.
    intent = SupervisorIntent.model_validate(
        {"target_agent": "planner", "plan": ["booking"]}
    )
    assert intent.plan is None


def test_plan_step_tier_gated_is_dropped():
    # A step outside allowed_subagents is dropped even when the target passes,
    # leaving only the primary task.
    narrow = replace(
        resolve_agent_context(tier="free"), allowed_subagents=frozenset({"concierge"})
    )
    agents = _task_agents_for(
        SupervisorIntent(target_agent="concierge", plan=["planner", "budget"]),
        narrow,
    )
    assert agents == ["concierge"]


def test_plan_length_capped_at_max_ledger_steps():
    # A model-emitted plan longer than the cap is truncated in code: primary plus
    # at most MAX_LEDGER_STEPS - 1 distinct follow-ons (duplicates skipped first).
    over_long = ["concierge", "planner", "budget", "journal", "concierge"]
    agents = _task_agents_for(
        SupervisorIntent(target_agent="planner", plan=over_long),
        AgentContext(),
    )
    # planner (dup of target) and the trailing concierge (dup) are dropped; the
    # remaining distinct follow-ons fill the cap.
    assert agents == ["planner", "concierge", "budget", "journal"]
    assert len(agents) == MAX_LEDGER_STEPS
    assert len(agents) - 1 == MAX_LEDGER_STEPS - 1  # follow-on count at the cap


def test_booking_target_queues_no_followons():
    # A booking target routes to HITL with no follow-ons (pre-ledger behavior).
    agents = _task_agents_for(
        SupervisorIntent(target_agent="booking", plan=["concierge", "budget"]),
        AgentContext(),
    )
    assert agents == ["booking"]


# ---------------------------------------------------------------------------
# (d) One-item plan yields two task agents
# ---------------------------------------------------------------------------


def test_one_item_plan_yields_two_tasks():
    ctx = AgentContext()
    one_item_plan = _task_agents_for(
        SupervisorIntent(target_agent="planner", plan=["concierge"]), ctx
    )
    assert one_item_plan == ["planner", "concierge"]


def test_no_plan_no_secondary_is_empty():
    assert _task_agents_for(
        SupervisorIntent(target_agent="concierge"), AgentContext()
    ) == ["concierge"]
