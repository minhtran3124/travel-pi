"""SC-29 — resume, not restart.

A ``running`` research row whose thread ``research:u1:t1`` carries a checkpoint is
resumed by ``ResearchService.resume`` with ``None`` input under a *new* run row
whose first step ``meta.resumed_from`` is the old run id, and the new run finishes
``completed``.
"""

from __future__ import annotations

import pytest
from app.clients.llm import FakeLLM
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models.agent_run import AgentRun
from app.repositories.agent_run import AgentRunRepository
from app.research.progress import ProgressBus
from app.research.service import ResearchService
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
