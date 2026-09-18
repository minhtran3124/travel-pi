"""SC-12 — ResearchService bookkeeping.

``start`` refuses a trip the caller does not own (``NotFoundError``), refuses a
second start while one is ``running`` (``ConflictError``), and otherwise returns a
``run_id``; ``latest`` returns that run; and ``sweep_stale`` flips a synthetically
aged ``running`` row to ``interrupted`` while leaving a fresh one alone.
"""

from __future__ import annotations

import pytest
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models.agent_run import AgentRun
from app.db.models.trip import Trip
from app.exceptions import ConflictError, NotFoundError
from app.research.progress import ProgressBus
from app.research.service import ResearchService
from langgraph.store.memory import InMemoryStore

OWNER = "u1"
TRIP = "t1"


@pytest.fixture
def factory(tmp_path):
    url = f"sqlite:///{tmp_path / 'service.db'}"
    Base.metadata.create_all(get_engine(url))
    sf = get_session_factory(url)
    with sf() as s:
        s.add(Trip(id=TRIP, user_id=OWNER, title="Trip", travelers=2))
        s.commit()
    return sf


@pytest.fixture
def service(factory):
    return ResearchService(
        session_factory=factory,
        store=InMemoryStore(),
        agent=None,
        bus=ProgressBus(),
    )


def _get(factory, run_id: str) -> AgentRun | None:
    with factory() as s:
        return s.get(AgentRun, run_id)


def test_start_refuses_foreign_trip(service) -> None:
    with pytest.raises(NotFoundError):
        service.start("someone-else", TRIP)


def test_start_returns_run_id_and_refuses_second_while_running(
    service, factory
) -> None:
    run_id = service.start(OWNER, TRIP)
    assert run_id

    row = _get(factory, run_id)
    assert row.status == "running"
    assert row.kind == "research"
    assert row.channel == "research"
    assert row.thread_id == f"research:{OWNER}:{TRIP}"

    with pytest.raises(ConflictError):
        service.start(OWNER, TRIP)


def test_latest_returns_the_started_run(service) -> None:
    run_id = service.start(OWNER, TRIP)
    latest = service.latest(TRIP)
    assert latest is not None
    assert latest.id == run_id


def test_sweep_stale_flips_only_aged_running_rows(service, factory) -> None:
    # An aged running run for a different trip (older than the 30-min threshold).
    aged_id = "run-aged"
    with factory() as s:
        s.add(
            AgentRun(
                id=aged_id,
                user_id=OWNER,
                conversation_id="research:u1:t2",
                thread_id="research:u1:t2",
                trip_id="t2",
                channel="research",
                kind="research",
                status="running",
                started_at="2020-01-01T00:00:00+00:00",
            )
        )
        s.commit()

    fresh_id = service.start(OWNER, TRIP)  # started_at ~ now

    swept = service.sweep_stale()
    assert swept == 1

    assert _get(factory, aged_id).status == "interrupted"
    assert _get(factory, fresh_id).status == "running"
