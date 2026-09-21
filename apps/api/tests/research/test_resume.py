"""SC-29 — resume, not restart.

A ``running`` research row whose thread ``research:u1:t1`` carries a checkpoint is
resumed by ``ResearchService.resume`` with ``None`` input under a *new* run row
whose first step ``meta.resumed_from`` is the old run id, and the new run finishes
``completed``.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.clients.llm import FakeLLM
from app.core.config import get_settings
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models.agent_run import AgentRun
from app.db.models.trip import Trip
from app.exceptions import ConflictError
from app.repositories.agent_run import AgentRunRepository
from app.research.agent import build_research_agent
from app.research.progress import ProgressBus
from app.research.service import ResearchService
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from tests.research.conftest import THREAD_CONFIG, TRIP_ID, USER_ID, build, context


@pytest.fixture
def factory(tmp_path):
    url = f"sqlite:///{tmp_path / 'resume.db'}"
    Base.metadata.create_all(get_engine(url))
    return get_session_factory(url)


def _seed_orphan_row(factory, run_id: str) -> None:
    AgentRunRepository(factory).start(
        run_id,
        user_id=USER_ID,
        conversation_id=f"research:{USER_ID}:{TRIP_ID}",
        thread_id=f"research:{USER_ID}:{TRIP_ID}",
        trip_id=TRIP_ID,
        channel="research",
        kind="research",
        started_at="2020-01-01T00:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_resume_continues_thread_under_new_run(factory) -> None:
    store = InMemoryStore()
    agent = build(
        store,
        llm=FakeLLM(responses=[{"content": "seeded"}]),
        grader=FakeLLM(responses=[{"content": "ok"}]),
    )

    # Establish a checkpoint on the dossier thread (empty rubric -> grader skipped).
    await agent.ainvoke(
        {
            "messages": [{"role": "user", "content": "start research"}],
            "rubric": "",
            "trip_id": TRIP_ID,
            "user_id": USER_ID,
            "preferences": "",
            "language": "en",
        },
        THREAD_CONFIG,
        context=context(),
    )

    old_run_id = "run-interrupted"
    _seed_orphan_row(factory, old_run_id)

    service = ResearchService(
        session_factory=factory,
        store=store,
        agent=agent,
        bus=ProgressBus(),
    )

    new_run_id = await service.resume(old_run_id)
    assert new_run_id != old_run_id

    with factory() as s:
        new_row = s.get(AgentRun, new_run_id)
    assert new_row.status == "completed"

    steps = AgentRunRepository(factory).steps_for(new_run_id)
    assert steps, "resume must record at least the marker step"
    assert steps[0].meta is not None
    assert steps[0].meta.get("resumed_from") == old_run_id


# -- a start after a crash resumes instead of 409ing (PR #221 review) ---------


class _ProcessDied(RuntimeError):
    pass


class _DiesOnSecondCall(FakeLLM):
    """Answers once with a todo write, then dies — the checkpoint is left mid-turn,
    the way a process killed during a run leaves it."""

    def _generate(self, *args, **kwargs):
        _DIES["calls"] += 1
        if _DIES["calls"] > 1:
            raise _ProcessDied("process died mid-run")
        return super()._generate(*args, **kwargs)


_DIES = {"calls": 0}


@pytest.fixture
def trip_factory(factory):
    with factory() as s:
        s.add(Trip(id=TRIP_ID, user_id=USER_ID, title="Trip", travelers=2))
        s.commit()
    return factory


def _agent(store, checkpointer, responses):
    return build_research_agent(
        store=store,
        checkpointer=checkpointer,
        llm=responses
        if isinstance(responses, FakeLLM)
        else FakeLLM(responses=responses),
        grader_llm=FakeLLM(responses=[{"content": "ok"}]),
    )


def _seed_recent_orphan(factory, run_id: str) -> None:
    """A row its process left ``running`` minutes ago — younger than the stale
    threshold, so the startup sweep leaves it alone."""
    AgentRunRepository(factory).start(
        run_id,
        user_id=USER_ID,
        conversation_id=f"research:{USER_ID}:{TRIP_ID}",
        thread_id=f"research:{USER_ID}:{TRIP_ID}",
        trip_id=TRIP_ID,
        channel="research",
        kind="research",
        started_at=datetime.now(UTC).isoformat(),
    )


@pytest.mark.asyncio
async def test_start_after_a_crash_resumes_the_checkpointed_turn(trip_factory) -> None:
    store, checkpointer = InMemoryStore(), MemorySaver()
    _DIES["calls"] = 0
    dying = _agent(
        store,
        checkpointer,
        _DiesOnSecondCall(
            responses=[
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "name": "write_todos",
                            "args": {
                                "todos": [{"content": "flights", "status": "pending"}]
                            },
                            "id": "t1",
                        }
                    ],
                }
            ]
        ),
    )
    with pytest.raises(_ProcessDied):
        await dying.ainvoke(
            {
                "messages": [{"role": "user", "content": "start research"}],
                "rubric": "",
                "trip_id": TRIP_ID,
                "user_id": USER_ID,
                "preferences": "",
                "language": "en",
            },
            THREAD_CONFIG,
            context=context(),
        )
    assert (await dying.aget_state(THREAD_CONFIG)).next, "checkpoint left mid-turn"
    _seed_recent_orphan(trip_factory, "run-orphan")

    # A fresh process: same checkpointer/store, empty bus.
    service = ResearchService(
        session_factory=trip_factory,
        store=store,
        agent=_agent(store, checkpointer, [{"content": "done"}]),
        bus=ProgressBus(),
    )
    new_run_id = service.start(USER_ID, TRIP_ID)

    with trip_factory() as s:
        assert s.get(AgentRun, "run-orphan").status == "interrupted"
    await service.launch(new_run_id, USER_ID, TRIP_ID, instruction="ignored on resume")

    with trip_factory() as s:
        assert s.get(AgentRun, new_run_id).status == "completed"
    steps = AgentRunRepository(trip_factory).steps_for(new_run_id)
    assert steps[0].meta.get("resumed_from") == "run-orphan"
    humans = [
        m.content
        for m in (await service._agent.aget_state(THREAD_CONFIG)).values["messages"]
        if m.type == "human"
    ]
    assert humans == ["start research"], "a resume adds no new turn"


@pytest.mark.asyncio
async def test_an_orphan_with_nothing_to_continue_runs_the_new_turn(
    trip_factory,
) -> None:
    """The process died before its turn reached a checkpoint: there is nothing to
    resume, so the caller's own turn runs instead of an empty resume."""
    store, checkpointer = InMemoryStore(), MemorySaver()
    _seed_recent_orphan(trip_factory, "run-orphan")
    service = ResearchService(
        session_factory=trip_factory,
        store=store,
        agent=_agent(store, checkpointer, [{"content": "done"}]),
        bus=ProgressBus(),
    )

    new_run_id = service.start(USER_ID, TRIP_ID)
    await service.launch(new_run_id, USER_ID, TRIP_ID, instruction="focus stays")

    humans = [
        m.content
        for m in (await service._agent.aget_state(THREAD_CONFIG)).values["messages"]
        if m.type == "human"
    ]
    assert humans == ["focus stays"]


def test_resuming_an_orphan_does_not_spend_the_daily_cap(
    trip_factory, monkeypatch
) -> None:
    monkeypatch.setenv("RESEARCH_DAILY_LIMIT", "1")
    get_settings.cache_clear()
    try:
        service = ResearchService(
            session_factory=trip_factory,
            store=InMemoryStore(),
            agent=None,
            bus=ProgressBus(),
        )
        service._spend_daily_cap(USER_ID)
        _seed_recent_orphan(trip_factory, "run-orphan")

        assert service.start(USER_ID, TRIP_ID)
    finally:
        get_settings.cache_clear()


def test_a_run_live_in_this_process_still_conflicts(trip_factory) -> None:
    bus = ProgressBus()
    _seed_recent_orphan(trip_factory, "run-live")
    bus.open("run-live")
    service = ResearchService(
        session_factory=trip_factory, store=InMemoryStore(), agent=None, bus=bus
    )

    with pytest.raises(ConflictError):
        service.start(USER_ID, TRIP_ID)
    with trip_factory() as s:
        assert s.get(AgentRun, "run-live").status == "running"
