"""Task 5 — background work moves to an Arq/Redis worker.

No Redis is needed: ``enqueue`` is faked, and the worker's job functions take a plain
``ctx`` dict. With ``REDIS_URL`` unset the old in-process behaviour must be unchanged.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.core import queue
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models.agent_run import AgentRun
from app.db.models.trip import Trip
from app.memory import dispatch
from app.research import launcher
from app.research.progress import ProgressBus
from app.research.service import ResearchService
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.store.memory import InMemoryStore

pytest.importorskip("arq")
from app import worker  # noqa: E402

OWNER = "u1"
TRIP = "t1"


def _redis(monkeypatch, url: str | None) -> None:
    monkeypatch.setattr(queue, "get_settings", lambda: SimpleNamespace(redis_url=url))


@pytest.fixture
def enqueue(monkeypatch) -> AsyncMock:
    fake = AsyncMock(return_value=True)
    monkeypatch.setattr(launcher, "enqueue", fake)
    monkeypatch.setattr(dispatch, "enqueue", fake)
    return fake


def _service_stub() -> MagicMock:
    service = MagicMock(name="ResearchService")
    service.launch = AsyncMock(name="launch")
    service.take_resume = MagicMock(return_value=None)
    return service


# -- queue seam ------------------------------------------------------------------


def test_queue_is_off_without_redis_url(monkeypatch) -> None:
    _redis(monkeypatch, None)
    assert queue.queue_enabled() is False
    _redis(monkeypatch, "")
    assert queue.queue_enabled() is False
    _redis(monkeypatch, "redis://localhost:6379")
    assert queue.queue_enabled() is True


@pytest.mark.asyncio
async def test_enqueue_is_idempotent_by_job_id(monkeypatch) -> None:
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(side_effect=[object(), None])
    monkeypatch.setattr(queue, "_pool", pool)

    assert await queue.enqueue("run_research", "a", job_id="run-1") is True
    assert await queue.enqueue("run_research", "a", job_id="run-1") is False
    for call in pool.enqueue_job.await_args_list:
        assert call.kwargs["_job_id"] == "run-1"


# -- research launch -------------------------------------------------------------


@pytest.mark.asyncio
async def test_research_runs_in_process_when_redis_unset(monkeypatch, enqueue) -> None:
    _redis(monkeypatch, None)
    service = _service_stub()

    await launcher.launch_research(
        service, "r1", OWNER, TRIP, instruction="x", language="en", origin="HCMC"
    )

    service.launch.assert_awaited_once_with(
        "r1", OWNER, TRIP, instruction="x", language="en", origin="HCMC"
    )
    enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_research_only_enqueues_when_redis_set(monkeypatch, enqueue) -> None:
    _redis(monkeypatch, "redis://x")
    service = _service_stub()
    service.take_resume.return_value = "old-run"

    await launcher.launch_research(
        service, "r1", OWNER, TRIP, instruction="x", language="vi", origin="HCMC"
    )

    service.launch.assert_not_called()
    enqueue.assert_awaited_once_with(
        "run_research", "r1", OWNER, TRIP, "x", "vi", "HCMC", "old-run", job_id="r1"
    )


@pytest.mark.asyncio
async def test_research_falls_back_in_process_when_redis_down(
    monkeypatch, enqueue
) -> None:
    _redis(monkeypatch, "redis://x")
    enqueue.side_effect = ConnectionError("redis down")
    service = _service_stub()

    await launcher.launch_research(service, "r1", OWNER, TRIP, language="en")

    service.launch.assert_awaited_once_with("r1", OWNER, TRIP, language="en")


@pytest.mark.asyncio
async def test_resume_id_survives_enqueue_failure_fallback(
    monkeypatch, enqueue
) -> None:
    _redis(monkeypatch, "redis://x")
    enqueue.side_effect = ConnectionError("redis down")
    service = _service_stub()
    resumes = {"r1": "old-run"}
    service.take_resume = MagicMock(side_effect=lambda rid: resumes.pop(rid, None))

    await launcher.launch_research(service, "r1", OWNER, TRIP, language="en")

    service.launch.assert_awaited_once_with(
        "r1", OWNER, TRIP, language="en", resumed_from="old-run"
    )


# -- memory extraction dispatch --------------------------------------------------


def _extraction_kwargs(**overrides) -> dict:
    kw = {
        "messages": [
            HumanMessage(content="I like window seats"),
            AIMessage(content="ok"),
        ],
        "user_id": "u1",
        "trip_id": "t1",
        "plan_approved": False,
        "allow_memory_write": True,
        "store": InMemoryStore(),
        "llm": MagicMock(),
        "run_id": "run-9",
        "session_factory": None,
    }
    kw.update(overrides)
    return kw


@pytest.mark.asyncio
async def test_memory_runs_in_process_when_redis_unset(monkeypatch, enqueue) -> None:
    _redis(monkeypatch, None)
    ran = MagicMock()
    monkeypatch.setattr(dispatch, "run_memory_extraction", ran)

    await dispatch.dispatch_memory_extraction(**_extraction_kwargs())

    ran.assert_called_once()
    assert ran.call_args.kwargs["run_id"] == "run-9"
    enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_memory_enqueues_serialised_messages_when_redis_set(
    monkeypatch, enqueue
) -> None:
    _redis(monkeypatch, "redis://x")
    ran = MagicMock()
    monkeypatch.setattr(dispatch, "run_memory_extraction", ran)

    await dispatch.dispatch_memory_extraction(**_extraction_kwargs())

    ran.assert_not_called()
    args = enqueue.await_args
    assert args.args[0] == "run_memory_extraction"
    assert args.args[1] == "run-9"
    assert args.args[2][0]["data"]["content"] == "I like window seats"
    assert args.kwargs == {"job_id": "memory:run-9"}


@pytest.mark.asyncio
async def test_memory_not_enqueued_when_writes_disallowed(monkeypatch, enqueue) -> None:
    _redis(monkeypatch, "redis://x")
    await dispatch.dispatch_memory_extraction(
        **_extraction_kwargs(allow_memory_write=False)
    )
    enqueue.assert_not_called()


@pytest.mark.asyncio
async def test_memory_stream_skips_empty_sink_and_pending_interrupt(
    monkeypatch, enqueue
) -> None:
    _redis(monkeypatch, "redis://x")
    kw = {
        k: v
        for k, v in _extraction_kwargs().items()
        if k not in {"messages", "user_id", "trip_id", "plan_approved"}
    }
    await dispatch.dispatch_memory_extraction_from_stream(sink={}, **kw)
    await dispatch.dispatch_memory_extraction_from_stream(
        sink={"interrupt_pending": True, "values": {"user_id": "u1"}}, **kw
    )
    enqueue.assert_not_called()


# -- worker jobs -----------------------------------------------------------------


@pytest.fixture
def factory(tmp_path):
    url = f"sqlite:///{tmp_path / 'worker.db'}"
    Base.metadata.create_all(get_engine(url))
    sf = get_session_factory(url)
    with sf() as s:
        s.add(Trip(id=TRIP, user_id=OWNER, title="Trip", travelers=2))
        s.commit()
    return sf


class _CrashingAgent:
    """Agent whose stream blows up, as a dying dependency would."""

    store = None

    async def astream_events(self, *a, **k):
        raise RuntimeError("provider down")


def _ctx(factory, agent) -> dict:
    bus = ProgressBus()
    service = ResearchService(
        session_factory=factory, store=InMemoryStore(), agent=agent, bus=bus
    )
    return {"service": service, "bus": bus}


@pytest.mark.asyncio
async def test_worker_drives_a_running_run_to_a_terminal_state(factory) -> None:
    ctx = _ctx(factory, _CrashingAgent())
    run_id = ctx["service"].start(OWNER, TRIP)

    await worker.run_research(ctx, run_id, OWNER, TRIP, None, "en", "HCMC", None)

    with factory() as s:
        assert s.get(AgentRun, run_id).status == "failed"  # never stuck "running"


@pytest.mark.asyncio
async def test_worker_replay_of_a_finished_run_is_a_no_op(factory) -> None:
    ctx = _ctx(factory, _CrashingAgent())
    run_id = ctx["service"].start(OWNER, TRIP)
    await worker.run_research(ctx, run_id, OWNER, TRIP)
    ctx["service"].launch = AsyncMock(name="launch")

    await worker.run_research(ctx, run_id, OWNER, TRIP)  # duplicate delivery
    await worker.run_research(ctx, "unknown-run", OWNER, TRIP)

    ctx["service"].launch.assert_not_called()


@pytest.mark.asyncio
async def test_worker_memory_job_rebuilds_messages(monkeypatch) -> None:
    from langchain_core.messages import messages_to_dict

    ran = MagicMock()
    monkeypatch.setattr(worker, "run_memory_extraction", ran)
    store, llm, sf = InMemoryStore(), MagicMock(), object()
    ctx = {"store": store, "llm": llm, "session_factory": sf}

    await worker.run_memory_extraction_job(
        ctx,
        "run-9",
        messages_to_dict([HumanMessage(content="hi")]),
        "u1",
        "t1",
        True,
    )

    kw = ran.call_args.kwargs
    assert [m.content for m in kw["messages"]] == ["hi"]
    assert (kw["run_id"], kw["plan_approved"], kw["allow_memory_write"]) == (
        "run-9",
        True,
        True,
    )
    assert kw["store"] is store and kw["llm"] is llm and kw["session_factory"] is sf


def test_worker_settings_register_the_jobs() -> None:
    names = {
        getattr(f, "name", None) or f.__name__ for f in worker.WorkerSettings.functions
    }
    assert names == {"run_research", "run_memory_extraction"}
    assert worker.WorkerSettings.max_tries == 1
