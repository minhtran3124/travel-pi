"""SC-11 — the background runner.

A scripted run finishes ``agent_runs.status == "completed"`` with at least one
``tool`` step and a terminal ``research_done`` bus event; a run that exceeds a tiny
``research_timeout_s`` finishes ``failed`` with ``error_type == "TimeoutError"`` and
the function itself never raises (it runs as a FastAPI ``BackgroundTask`` — awaited
directly here, so a leaked exception would surface as a test error).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from app.clients.llm import FakeLLM
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models.agent_run import AgentRun
from app.repositories.agent_run import AgentRunRepository
from app.research import runner as runner_mod
from app.research.progress import ProgressBus
from app.research.runner import run_trip_research
from app.streaming.research_events import ResearchDone, ResearchError
from langgraph.store.memory import InMemoryStore

from tests.research.conftest import USER_ID, build, context


def _factory(tmp_path):
    url = f"sqlite:///{tmp_path / 'runner.db'}"
    Base.metadata.create_all(get_engine(url))
    return get_session_factory(url)


def _seed_running_row(factory, run_id: str) -> None:
    AgentRunRepository(factory).start(
        run_id,
        user_id=USER_ID,
        conversation_id="research:u1:t1",
        thread_id="research:u1:t1",
        trip_id="t1",
        channel="research",
        kind="research",
        started_at="2020-01-01T00:00:00+00:00",
    )


def _get_run(factory, run_id: str) -> AgentRun | None:
    with factory() as s:
        return s.get(AgentRun, run_id)


def _tool_call(name: str, args: dict, call_id: str) -> dict:
    return {"content": "", "tool_calls": [{"name": name, "args": args, "id": call_id}]}


def _buffered(bus: ProgressBus, run_id: str) -> list:
    return list(bus._runs[run_id].buffer)


@pytest.mark.asyncio
async def test_scripted_run_completes_with_tool_step_and_done_event(tmp_path) -> None:
    factory = _factory(tmp_path)
    run_id = "run-ok"
    _seed_running_row(factory, run_id)

    store = InMemoryStore()
    model = FakeLLM(
        responses=[
            _tool_call(
                "write_todos",
                {"todos": [{"content": "research the trip", "status": "in_progress"}]},
                "todos",
            ),
            {"content": "dossier ready"},
        ]
    )
    agent = build(store, llm=model, grader=FakeLLM(responses=[{"content": "ok"}]))
    bus = ProgressBus()

    await run_trip_research(
        run_id=run_id,
        ctx=context(),
        instruction="research my trip in depth",
        agent=agent,
        bus=bus,
        session_factory=factory,
    )

    row = _get_run(factory, run_id)
    assert row is not None
    assert row.status == "completed"

    steps = AgentRunRepository(factory).steps_for(run_id)
    assert any(step.kind == "tool" for step in steps)

    events = _buffered(bus, run_id)
    assert any(isinstance(e, ResearchDone) and e.status == "completed" for e in events)


@pytest.mark.asyncio
async def test_timeout_finishes_failed_and_never_raises(tmp_path, monkeypatch) -> None:
    factory = _factory(tmp_path)
    run_id = "run-timeout"
    _seed_running_row(factory, run_id)

    # A tiny timeout; the stub agent's stream sleeps well past it.
    monkeypatch.setattr(
        runner_mod,
        "get_settings",
        lambda: SimpleNamespace(research_timeout_s=0.01),
    )

    async def _never():  # pragma: no cover - never reached (timeout fires first)
        return
        yield

    class _SleepAgent:
        store = InMemoryStore()

        async def astream_events(self, inp, config=None, *, version, context=None):
            await asyncio.sleep(0.5)
            return _never()

    bus = ProgressBus()

    # Must return normally, not raise, even though the run times out.
    await run_trip_research(
        run_id=run_id,
        ctx=context(),
        instruction="research",
        agent=_SleepAgent(),
        bus=bus,
        session_factory=factory,
    )

    row = _get_run(factory, run_id)
    assert row is not None
    assert row.status == "failed"

    steps = AgentRunRepository(factory).steps_for(run_id)
    assert any(step.error_type == "TimeoutError" for step in steps)

    events = _buffered(bus, run_id)
    assert any(
        isinstance(e, ResearchError) and e.code == "TimeoutError" for e in events
    )
