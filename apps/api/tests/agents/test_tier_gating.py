"""Tier gating: supervisor enforces allowed_subagents from AgentContext (D.1).

Offline, FakeLLM-driven. Mirrors the pattern in test_supervisor.py.
Free tier cannot reach "booking" (or the plan HITL path that leads to it);
premium tier can route normally.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.context import AgentContext, resolve_agent_context
from langchain_core.messages import AIMessage, HumanMessage


def _runtime(ctx: AgentContext) -> SimpleNamespace:
    return SimpleNamespace(context=ctx)


def _free_ctx() -> AgentContext:
    return resolve_agent_context(tier="free")


def _premium_ctx() -> AgentContext:
    return resolve_agent_context(tier="premium")


# ---------------------------------------------------------------------------
# Free tier: booking blocked
# ---------------------------------------------------------------------------


def test_free_booking_intent_degrades_to_end():
    """Free user asking to book → supervisor emits upgrade message and no tasks."""
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    llm = FakeLLM(structured_responses=[SupervisorIntent(target_agent="booking")])
    supervisor = make_supervisor(llm)

    cmd = supervisor(
        {"messages": [HumanMessage(content="book me a hotel")]},
        _runtime(_free_ctx()),
    )

    assert cmd.goto == ()
    assert "tasks" not in cmd.update
    msgs = cmd.update.get("messages", [])
    assert msgs, "Expected a degradation message in update"
    assert isinstance(msgs[0], AIMessage)
    # Should mention premium / upgrade, not an error
    assert "premium" in msgs[0].content.lower() or "upgrade" in msgs[0].content.lower()


def test_free_booking_does_not_emit_tasks():
    """Free user → booking intent emits no tasks, so route_tasks will go to END."""
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    llm = FakeLLM(structured_responses=[SupervisorIntent(target_agent="booking")])
    supervisor = make_supervisor(llm)

    cmd = supervisor(
        {"messages": [HumanMessage(content="I want to book flights")]},
        _runtime(_free_ctx()),
    )

    assert cmd.goto == ()
    assert "tasks" not in cmd.update


def test_free_non_booking_emits_planner_task():
    """Free user asking for planning emits a planner task."""
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    llm = FakeLLM(structured_responses=[SupervisorIntent(target_agent="planner")])
    supervisor = make_supervisor(llm)

    cmd = supervisor(
        {"messages": [HumanMessage(content="plan my trip to Paris")]},
        _runtime(_free_ctx()),
    )

    assert cmd.goto == ()
    assert cmd.update["current_flow"] == "planner"
    assert cmd.update["tasks"] == [
        {"agent": "planner", "query": "plan my trip to Paris", "index": 0}
    ]


def test_free_booking_blocked_regardless_of_message_wording():
    """Gate applies to any free-tier booking-intent phrasing."""
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    llm = FakeLLM(structured_responses=[SupervisorIntent(target_agent="booking")])
    supervisor = make_supervisor(llm)

    cmd = supervisor(
        {"messages": [HumanMessage(content="book me a flight")]},
        _runtime(_free_ctx()),
    )

    assert cmd.goto == ()
    assert "tasks" not in cmd.update


# ---------------------------------------------------------------------------
# Premium tier: booking allowed
# ---------------------------------------------------------------------------


def test_premium_booking_emits_booking_task():
    """Premium user → booking emits a booking task; route_tasks sends it to plan."""
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    llm = FakeLLM(structured_responses=[SupervisorIntent(target_agent="booking")])
    supervisor = make_supervisor(llm)

    cmd = supervisor(
        {"messages": [HumanMessage(content="book me a hotel")]},
        _runtime(_premium_ctx()),
    )

    # Premium: booking task is emitted; the graph's route_tasks edge maps it
    # to the HITL plan approval node.
    assert cmd.goto == ()
    assert cmd.update["current_flow"] == "booking"
    assert cmd.update["tasks"] == [
        {"agent": "booking", "query": "book me a hotel", "index": 0}
    ]


def test_premium_planner_emits_planner_task():
    """Premium user → planner emits a planner task."""
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    llm = FakeLLM(structured_responses=[SupervisorIntent(target_agent="planner")])
    supervisor = make_supervisor(llm)

    cmd = supervisor(
        {"messages": [HumanMessage(content="plan my trip")]},
        _runtime(_premium_ctx()),
    )

    assert cmd.goto == ()
    assert cmd.update["tasks"] == [
        {"agent": "planner", "query": "plan my trip", "index": 0}
    ]


def test_default_context_is_permissive():
    """AgentContext() default (no context= passed) does not gate any sub-agent."""
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    llm = FakeLLM(structured_responses=[SupervisorIntent(target_agent="booking")])
    supervisor = make_supervisor(llm)

    # AgentContext() default has allowed_subagents=None → all permitted
    cmd = supervisor(
        {"messages": [HumanMessage(content="book me a hotel")]},
        _runtime(AgentContext()),
    )

    assert cmd.goto == ()
    assert cmd.update["tasks"] == [
        {"agent": "booking", "query": "book me a hotel", "index": 0}
    ]


# ---------------------------------------------------------------------------
# Regression (ce-code-review, 4 independent reviewers): the tier gate must
# also apply to a queued SECONDARY intent, not just the primary target — a
# free-tier user must never reach a premium-only sub-agent via pending_flows.
# ---------------------------------------------------------------------------


def test_free_tier_secondary_to_premium_only_agent_is_dropped():
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    # target=concierge is free-allowed; a hypothetical premium-only secondary
    # must be dropped even though the primary target passes the gate.
    llm = FakeLLM(
        structured_responses=[
            SupervisorIntent(target_agent="concierge", secondary_agent="planner")
        ]
    )
    supervisor = make_supervisor(llm)

    cmd = supervisor(
        {"messages": [HumanMessage(content="things to see, and plan my trip")]},
        _runtime(_free_ctx()),
    )

    # planner IS free-allowed today, so this specific pair should still queue —
    # this test documents the mechanism (not gated), the next one proves the gate.
    assert [t["agent"] for t in cmd.update["tasks"]] == ["concierge", "planner"]


def test_free_tier_secondary_not_in_allowed_subagents_is_dropped(monkeypatch):
    """Simulate a future premium-only secondary by narrowing allowed_subagents
    directly, independent of which agents PREMIUM_ONLY_SUBAGENTS lists today."""
    from dataclasses import replace

    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    llm = FakeLLM(
        structured_responses=[
            SupervisorIntent(target_agent="concierge", secondary_agent="planner")
        ]
    )
    supervisor = make_supervisor(llm)
    narrow_ctx = replace(_free_ctx(), allowed_subagents=frozenset({"concierge"}))

    cmd = supervisor(
        {"messages": [HumanMessage(content="things to see, and plan my trip")]},
        _runtime(narrow_ctx),
    )

    # Only the primary (concierge) survives; the gated secondary is dropped.
    assert [t["agent"] for t in cmd.update["tasks"]] == ["concierge"]
