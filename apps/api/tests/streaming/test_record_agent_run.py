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
    """Stand-in ``TurnMetricsHandler`` exposing only the ``snapshot()`` the recorder uses."""

    def __init__(self, snap: dict | None = None) -> None:
        self._snap = snap or {"llm_calls": 2, "input_tokens": 30, "output_tokens": 8}

    def snapshot(self) -> dict:
        return self._snap


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
