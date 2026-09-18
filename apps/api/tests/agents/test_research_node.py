"""Chat node ``research`` (trip-research-deep-agent, Task 6.1, SC-18).

The launcher makes **no** LLM call: the supervisor already routed the intent. It
books a background run through ``ResearchService.start`` and replies with
code-authored copy. These tests drive the node function directly with a stub
service factory, so nothing touches the DB or the network. ``language=None`` keeps
``system_reply`` on the English source (no translation store lookup).

The free-tier guarantee is enforced one step earlier, by the supervisor's
``allowed_subagents`` gate (research is premium-only), so the node is never
reached and ``start`` is never called — asserted here against the real supervisor.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.agents.constants import (
    RESEARCH_NEEDS_TRIP_MSG,
    RESEARCH_STARTED_MSG,
    RESEARCH_UNAVAILABLE_MSG,
)
from app.agents.context import AgentContext, resolve_agent_context
from app.enums import Tier
from app.exceptions import ConflictError
from app.research import launcher
from app.research.launcher import make_research_node
from langchain_core.messages import AIMessage, HumanMessage

OWNER = "u_research"
TRIP = "trip-1"


def _flag(monkeypatch, *, enabled: bool) -> None:
    """Point the launcher's settings read at a fixed ``research_enabled`` value."""
    monkeypatch.setattr(
        launcher, "get_settings", lambda: SimpleNamespace(research_enabled=enabled)
    )


def _state(**overrides) -> dict:
    state = {
        "messages": [HumanMessage(content="research my whole trip in depth")],
        "user_id": OWNER,
        "trip_id": TRIP,
        "language": None,
    }
    state.update(overrides)
    return state


def _service_factory() -> tuple[MagicMock, callable]:
    """A stub ``ResearchService`` whose ``start`` records its calls, and a factory
    returning it. The factory itself is a MagicMock so "never constructed" is
    provable, not just "start never called"."""
    service = MagicMock(name="ResearchService")
    factory = MagicMock(name="service_factory", return_value=service)
    return service, factory


# -- flag off -----------------------------------------------------------------


def test_flag_off_replies_unavailable_and_never_touches_the_service(monkeypatch):
    _flag(monkeypatch, enabled=False)
    service, factory = _service_factory()

    result = make_research_node(factory)(_state())

    assert result["messages"][0].content == RESEARCH_UNAVAILABLE_MSG
    assert "current_flow" not in result
    assert not result.get("awaiting_user")
    factory.assert_not_called()
    service.start.assert_not_called()


# -- no active trip -----------------------------------------------------------


def test_no_trip_asks_the_traveller_and_never_starts(monkeypatch):
    _flag(monkeypatch, enabled=True)
    service, factory = _service_factory()

    result = make_research_node(factory)(_state(trip_id=None))

    assert result["awaiting_user"] is True
    assert result["messages"][0].content == RESEARCH_NEEDS_TRIP_MSG
    factory.assert_not_called()
    service.start.assert_not_called()


def test_empty_string_trip_is_treated_as_no_trip(monkeypatch):
    _flag(monkeypatch, enabled=True)
    service, factory = _service_factory()

    result = make_research_node(factory)(_state(trip_id=""))

    assert result["awaiting_user"] is True
    service.start.assert_not_called()


# -- premium + trip: exactly one job -----------------------------------------


def test_premium_with_trip_starts_exactly_one_job(monkeypatch):
    _flag(monkeypatch, enabled=True)
    service, factory = _service_factory()

    result = make_research_node(factory)(_state())

    service.start.assert_called_once_with(OWNER, TRIP)
    assert result["current_flow"] == "research"
    msg = result["messages"][0]
    assert isinstance(msg, AIMessage)
    assert msg.content == RESEARCH_STARTED_MSG
    # The guard flag reflection reads to end the turn (no second job on a REVISE).
    assert msg.additional_kwargs.get("research_started") is True


def test_already_running_is_reassured_not_errored(monkeypatch):
    """A ConflictError (a run is already in flight) is not a 500: reply with the
    same 'started' copy and set the guard, so a REVISE cannot launch a second."""
    _flag(monkeypatch, enabled=True)
    service, factory = _service_factory()
    service.start.side_effect = ConflictError("already running")

    result = make_research_node(factory)(_state())

    service.start.assert_called_once_with(OWNER, TRIP)
    msg = result["messages"][0]
    assert msg.content == RESEARCH_STARTED_MSG
    assert msg.additional_kwargs.get("research_started") is True
    assert result["current_flow"] == "research"


# -- free tier: gated at the supervisor, node never reached -------------------


def _runtime(ctx: AgentContext) -> SimpleNamespace:
    return SimpleNamespace(context=ctx)


def test_free_tier_gets_the_premium_notice_and_no_job_starts(monkeypatch):
    """research is premium-only: the free tier is degraded by the supervisor's
    allowed_subagents gate before ever reaching the launcher, so no job starts."""
    from app.agents.supervisor import SupervisorIntent, make_supervisor
    from app.clients.llm import FakeLLM

    # Guard: if the launcher were ever reached, start would raise.
    _flag(monkeypatch, enabled=True)
    service, factory = _service_factory()
    service.start.side_effect = AssertionError("launcher must not run on free tier")

    ctx = resolve_agent_context(tier=Tier.FREE)
    assert "research" not in (ctx.allowed_subagents or frozenset())

    supervisor = make_supervisor(
        FakeLLM(structured_responses=[SupervisorIntent(target_agent="research")])
    )
    cmd = supervisor(
        {"messages": [HumanMessage(content="research my whole trip in depth")]},
        _runtime(ctx),
    )

    # Degraded to the code-authored upgrade notice; no tasks, so route_tasks never
    # dispatches the research node.
    assert "tasks" not in cmd.update
    assert cmd.update["messages"][0].content
    service.start.assert_not_called()
    factory.assert_not_called()
