"""``record_agent_run`` pass-through + status derivation (specs/agent-turn-metrics §4.5).

Drives the recorder with a scripted async SSE iterator against a real
``AgentRunRepository`` on a tmp SQLite factory, asserting the closed row's status
per scenario (completed / interrupted / failed / cancelled) and that every event
passes through unchanged.
"""

from __future__ import annotations

import asyncio

import pytest
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models import AgentRun
from app.repositories.agent_run import AgentRunRepository
from app.streaming import events
from app.streaming.agent_run import record_agent_run


class _FakeMetrics:
    """Stand-in ``TurnMetricsHandler`` with the surface the recorder actually uses.

    ``close_if_open`` / ``cost_usd`` are part of that surface: the recorder closes
    and prices the turn before persisting so a failed turn is not written with a
    NULL latency. A stub missing them would silently exercise the recorder's
    exception fallback and prove nothing.
    """

    def __init__(self, snap: dict | None = None) -> None:
        self._snap = snap or {"llm_calls": 2, "input_tokens": 30, "output_tokens": 8}
        self.latency_ms: int | None = None
        self.cost_usd: float | None = None

    def close_if_open(self) -> None:
        if self.latency_ms is None:
            self.latency_ms = 7

    def snapshot(self) -> dict:
        return {**self._snap, "latency_ms": self.latency_ms, "cost_usd": self.cost_usd}


@pytest.fixture
def factory(tmp_path):
    url = f"sqlite:///{tmp_path / 'agent_run.db'}"
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    return get_session_factory(url)


def _start_row(factory, run_id="run-1"):
    AgentRunRepository(factory).start(
        run_id,
        user_id="u1",
        conversation_id="c1",
        thread_id="t1",
        trip_id=None,
        channel="stream",
        kind="turn",
        started_at="2026-09-03T00:00:00+00:00",
    )


async def _script(items):
    for ev in items:
        yield ev


async def _drain(events_iter, *, run_id, metrics, factory):
    out = []
    async for ev in record_agent_run(
        events_iter, run_id=run_id, metrics=metrics, session_factory=factory
    ):
        out.append(ev)
    return out


def _row(factory, run_id="run-1") -> AgentRun:
    with factory() as s:
        return s.get(AgentRun, run_id)


def test_completed_status_and_passthrough(factory):
    _start_row(factory)
    items = [
        events.start("c1"),
        events.token("hi"),
        events.done(conversation_id="c1", current_flow="planner", suggestions=[]),
    ]
    out = asyncio.run(
        _drain(_script(items), run_id="run-1", metrics=_FakeMetrics(), factory=factory)
    )
    # Events pass through unchanged (same objects, same order).
    assert out == items
    row = _row(factory)
    assert row.status == "completed"
    assert row.current_flow == "planner"
    assert row.llm_calls == 2
    assert row.finished_at is not None


def test_interrupt_event_marks_interrupted(factory):
    _start_row(factory)
    items = [
        events.start("c1"),
        events.interrupt(conversation_id="c1", payload={"plan": "approve?"}),
        events.done(conversation_id="c1", current_flow="booking", suggestions=[]),
    ]
    asyncio.run(
        _drain(_script(items), run_id="run-1", metrics=_FakeMetrics(), factory=factory)
    )
    assert _row(factory).status == "interrupted"


def test_error_event_marks_failed(factory):
    _start_row(factory)
    items = [
        events.start("c1"),
        events.token("partial"),
        events.error(code="internal", message="boom"),
    ]
    asyncio.run(
        _drain(_script(items), run_id="run-1", metrics=_FakeMetrics(), factory=factory)
    )
    assert _row(factory).status == "failed"


def test_cancelled_marks_failed_and_reraises(factory):
    _start_row(factory)

    async def _run():
        gen = record_agent_run(
            _script([events.start("c1"), events.token("x")]),
            run_id="run-1",
            metrics=_FakeMetrics(),
            session_factory=factory,
        )
        await gen.__anext__()  # consume the start event
        with pytest.raises(asyncio.CancelledError):
            await gen.athrow(asyncio.CancelledError)

    asyncio.run(_run())
    assert _row(factory).status == "failed"


def test_aclose_midstream_marks_failed(factory):
    _start_row(factory)

    async def _run():
        gen = record_agent_run(
            _script([events.start("c1"), events.token("x")]),
            run_id="run-1",
            metrics=_FakeMetrics(),
            session_factory=factory,
        )
        await gen.__anext__()
        await gen.aclose()

    asyncio.run(_run())
    assert _row(factory).status == "failed"


def test_repo_error_is_swallowed(factory, caplog):
    """A failing ``finish`` must be logged, never raised into the stream."""

    class _BadMetrics:
        def snapshot(self):
            raise RuntimeError("snapshot blew up")

    _start_row(factory)
    items = [
        events.start("c1"),
        events.done(conversation_id="c1", current_flow=None, suggestions=[]),
    ]
    # Must not raise despite snapshot() failing inside the finally.
    out = asyncio.run(
        _drain(_script(items), run_id="run-1", metrics=_BadMetrics(), factory=factory)
    )
    assert [e.event for e in out] == ["start", "done"]


def test_failed_turn_still_records_latency(factory):
    """A crashed stream must not persist a NULL latency.

    The mapper's metrics block only runs on the success path, so without the
    recorder closing the handler itself every failed turn would drop out of the
    dashboard's latency and cost rollups. Uses the REAL handler, not the stub.
    """
    from app.agents.metrics import TurnMetricsHandler

    _start_row(factory, "run-fail")
    metrics = TurnMetricsHandler()

    async def _boom():
        yield events.start("c1")
        raise RuntimeError("graph exploded")

    with pytest.raises(RuntimeError):
        asyncio.run(_drain(_boom(), run_id="run-fail", metrics=metrics, factory=factory))

    row = _row(factory, "run-fail")
    assert row.status == "failed"
    assert row.latency_ms is not None and row.latency_ms >= 0


def test_success_path_keeps_the_owner_latency(factory):
    """close_if_open must not overwrite a latency the mapper already set."""
    from app.agents.metrics import TurnMetricsHandler

    _start_row(factory, "run-ok")
    metrics = TurnMetricsHandler()
    metrics.latency_ms = 4242  # as the mapper's close(started) would have set it

    asyncio.run(
        _drain(
            _script([events.start("c1"), events.done(conversation_id="c1", current_flow="planner", suggestions=[])]),
            run_id="run-ok",
            metrics=metrics,
            factory=factory,
        )
    )
    assert _row(factory, "run-ok").latency_ms == 4242


def test_anthropic_usage_shape_is_priced_and_cache_read_lands_in_cached():
    """Claude usage (langchain-anthropic shape) → cached bucket + non-None cost.

    langchain-anthropic already folds ``cache_read`` into ``input_tokens`` and
    streams the bare model id in ``response_metadata["model_name"]`` — both are
    what ``pricing.estimate_cost`` assumes (specs/anthropic-provider T7).
    """
    from uuid import uuid4

    from app.agents.metrics import TurnMetricsHandler
    from app.core.pricing import estimate_cost
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult

    metrics = TurnMetricsHandler()
    run_id = uuid4()
    metrics.on_chat_model_start({}, [[]], run_id=run_id, metadata={})
    msg = AIMessage(
        content=[{"type": "text", "text": "hi"}],
        usage_metadata={
            "input_tokens": 1000,  # includes the 400 cache-read tokens
            "output_tokens": 50,
            "total_tokens": 1050,
            "input_token_details": {"cache_read": 400, "cache_creation": 0},
        },
        response_metadata={"model_name": "claude-sonnet-5-5"},
    )
    metrics.on_llm_end(
        LLMResult(generations=[[ChatGeneration(message=msg)]]), run_id=run_id
    )

    snap = metrics.snapshot()
    assert snap["by_model"]["claude-sonnet-5-5"]["cached_tokens"] == 400
    assert snap["cached_tokens"] == 400
    cost = estimate_cost(snap["by_model"])
    assert cost is not None
    # (1000-400)*2.00 + 400*0.20 + 50*10.00 per 1M
    assert cost == pytest.approx((600 * 2.0 + 400 * 0.2 + 50 * 10.0) / 1e6)
