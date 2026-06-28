"""Tier gating: supervisor enforces allowed_subagents from AgentContext (D.1).

Offline, FakeLLM-driven. Mirrors the pattern in test_supervisor.py.
Free tier cannot reach "booking" (or the plan HITL path that leads to it);
premium tier can route normally.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.agents.context import AgentContext, resolve_agent_context
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END


def _runtime(ctx: AgentContext) -> SimpleNamespace:
    return SimpleNamespace(context=ctx)


def _free_ctx(mode: str = "balanced") -> AgentContext:
    return resolve_agent_context(tier="free", mode=mode)


def _premium_ctx(mode: str = "balanced") -> AgentContext:
    return resolve_agent_context(tier="premium", mode=mode)


# ---------------------------------------------------------------------------
# Free tier: booking blocked
# ---------------------------------------------------------------------------


def test_free_booking_intent_degrades_to_end():
    """Free user asking to book → supervisor returns END with upgrade message."""
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    llm = FakeLLM(structured_responses=[SupervisorIntent(target_agent="booking")])
    supervisor = make_supervisor(llm)

    cmd = supervisor(
        {"messages": [HumanMessage(content="book me a hotel")]},
        _runtime(_free_ctx()),
    )

    assert cmd.goto == END
    msgs = cmd.update.get("messages", [])
    assert msgs, "Expected a degradation message in update"
    assert isinstance(msgs[0], AIMessage)
    # Should mention premium / upgrade, not an error
    assert "premium" in msgs[0].content.lower() or "upgrade" in msgs[0].content.lower()


def test_free_booking_does_not_route_to_plan():
    """Free user → booking intent must NOT route to the plan HITL node."""
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    llm = FakeLLM(structured_responses=[SupervisorIntent(target_agent="booking")])
    supervisor = make_supervisor(llm)

    cmd = supervisor(
        {"messages": [HumanMessage(content="I want to book flights")]},
        _runtime(_free_ctx()),
    )

    assert cmd.goto != "plan"
    assert cmd.goto != "booking"


def test_free_non_booking_routes_normally():
    """Free user asking for planning still routes to planner."""
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    llm = FakeLLM(structured_responses=[SupervisorIntent(target_agent="planner")])
    supervisor = make_supervisor(llm)

    cmd = supervisor(
        {"messages": [HumanMessage(content="plan my trip to Paris")]},
        _runtime(_free_ctx()),
    )

    assert cmd.goto == "planner"
    assert cmd.update["current_flow"] == "planner"


def test_free_fast_booking_also_blocked():
    """Gate applies across all free modes (fast included)."""
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    llm = FakeLLM(structured_responses=[SupervisorIntent(target_agent="booking")])
    supervisor = make_supervisor(llm)

    cmd = supervisor(
        {"messages": [HumanMessage(content="book me a flight")]},
        _runtime(_free_ctx(mode="fast")),
    )

    assert cmd.goto == END


# ---------------------------------------------------------------------------
# Premium tier: booking allowed
# ---------------------------------------------------------------------------


def test_premium_booking_routes_to_plan():
    """Premium user → booking routes through the HITL plan node."""
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    llm = FakeLLM(structured_responses=[SupervisorIntent(target_agent="booking")])
    supervisor = make_supervisor(llm)

    cmd = supervisor(
        {"messages": [HumanMessage(content="book me a hotel")]},
        _runtime(_premium_ctx()),
    )

    # Premium: booking is gated through HITL plan approval node
    assert cmd.goto == "plan"
    assert cmd.update["current_flow"] == "booking"


def test_premium_planner_routes_normally():
    """Premium user → planner routes directly."""
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    llm = FakeLLM(structured_responses=[SupervisorIntent(target_agent="planner")])
    supervisor = make_supervisor(llm)

    cmd = supervisor(
        {"messages": [HumanMessage(content="plan my trip")]},
        _runtime(_premium_ctx()),
    )

    assert cmd.goto == "planner"


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

    assert cmd.goto == "plan"
