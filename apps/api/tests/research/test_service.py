"""SC-12 — ResearchService bookkeeping.

``start`` refuses a trip the caller does not own (``NotFoundError``), refuses a
second start while one is ``running`` (``ConflictError``), and otherwise returns a
``run_id``; ``latest`` returns that run; and ``sweep_stale`` flips a synthetically
aged ``running`` row to ``interrupted`` while leaving a fresh one alone.
"""

from __future__ import annotations

import pytest
from app.core.config import get_settings
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models.agent_run import AgentRun
from app.db.models.trip import Trip
from app.exceptions import ConflictError, NotFoundError, RateLimitError
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


def test_runnable_reflects_whether_an_agent_was_built(factory) -> None:
    """The chat node checks ``runnable`` before booking, so a run is never stranded
    when no research agent was built (flag off / build failed)."""
    store = InMemoryStore()
    assert (
        ResearchService(
            session_factory=factory, store=store, agent=None, bus=ProgressBus()
        ).runnable
        is False
    )
    assert (
        ResearchService(
            session_factory=factory,
            store=store,
            agent=object(),
            bus=ProgressBus(),
        ).runnable
        is True
    )


@pytest.mark.asyncio
async def test_launch_drives_the_runner_for_the_booked_run(
    service, factory, monkeypatch
) -> None:
    """``launch`` is what the chat node schedules after ``start``; it must actually
    invoke the runner for that run id (a fresh turn, ``resumed_from=None``)."""
    from app.research import runner as runner_mod

    run_id = service.start(OWNER, TRIP)

    calls: list[dict] = []

    async def fake_runner(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(runner_mod, "run_trip_research", fake_runner)

    await service.launch(run_id, OWNER, TRIP)

    assert len(calls) == 1
    assert calls[0]["run_id"] == run_id
    assert calls[0]["resumed_from"] is None
    assert calls[0]["ctx"].trip_id == TRIP
    assert calls[0]["ctx"].user_id == OWNER


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


def _complete(factory, run_id: str) -> None:
    with factory() as s:
        s.get(AgentRun, run_id).status = "completed"
        s.commit()


@pytest.fixture
def daily_limit(monkeypatch):
    monkeypatch.setenv("RESEARCH_DAILY_LIMIT", "2")
    get_settings.cache_clear()
    yield 2
    get_settings.cache_clear()


def test_start_enforces_the_daily_cap_for_every_caller(
    service, factory, daily_limit
) -> None:
    """The cap lives in ``start`` itself, so the REST start, the REST revise and the
    chat launcher are all bounded — before, only the start route's dependency
    counted, and revise or chat booked unlimited multi-minute LLM runs."""
    for _ in range(daily_limit):
        _complete(factory, service.start(OWNER, TRIP))

    with pytest.raises(RateLimitError):
        service.start(OWNER, TRIP)


def test_a_conflicting_start_does_not_spend_the_daily_cap(
    service, factory, daily_limit
) -> None:
    run_id = service.start(OWNER, TRIP)
    for _ in range(3):
        with pytest.raises(ConflictError):
            service.start(OWNER, TRIP)
    _complete(factory, run_id)

    assert service.start(OWNER, TRIP)


def test_start_makes_the_run_live_on_the_bus_before_any_event(factory) -> None:
    """The Research tab opens the stream on the 202, before the runner's first event.
    If the run is not live on the bus by then, the SSE route takes the snapshot
    branch for the whole run and the tab never sees tool/subagent/file progress."""
    bus = ProgressBus()
    service = ResearchService(
        session_factory=factory, store=InMemoryStore(), agent=None, bus=bus
    )

    run_id = service.start(OWNER, TRIP)

    assert bus.has(run_id) is True


def test_a_refused_start_opens_no_channel(service, factory) -> None:
    service.start(OWNER, TRIP)
    with pytest.raises(ConflictError):
        service.start(OWNER, TRIP)
    assert len(service._bus._runs) == 1


def test_the_loser_of_a_concurrent_start_does_not_spend_the_daily_cap(
    service, factory, daily_limit, monkeypatch
) -> None:
    """Two clicks race: both see no running row, then the winner books while the
    loser waits on the per-trip lock and wakes to a 409. The loser launched
    nothing, so it must not have spent a slot of the daily cap."""
    import app.research.service as service_mod

    real_lock = service_mod.advisory_xact_lock
    winner: list[str] = []

    def winner_books_while_we_wait(session, name):
        real_lock(session, name)
        with factory() as other:
            other.add(
                AgentRun(
                    id="winner",
                    user_id=OWNER,
                    conversation_id=f"research:{OWNER}:{TRIP}",
                    thread_id=f"research:{OWNER}:{TRIP}",
                    trip_id=TRIP,
                    channel="research",
                    kind="research",
                    status="running",
                    started_at="2026-09-21T00:00:00+00:00",
                )
            )
            other.commit()
        winner.append("winner")
        service._bus.open("winner")

    monkeypatch.setattr(service_mod, "advisory_xact_lock", winner_books_while_we_wait)
    with pytest.raises(ConflictError):
        service.start(OWNER, TRIP)
    monkeypatch.setattr(service_mod, "advisory_xact_lock", real_lock)
    assert winner == ["winner"]
    _complete(factory, "winner")

    for _ in range(daily_limit):
        _complete(factory, service.start(OWNER, TRIP))


def test_chat_state_running_live_vs_not_live(service, factory) -> None:
    """A chat turn reports ``"running"`` only while this process drives the run (live
    on the bus). Once the channel is gone (the driving turn ended, e.g. cancelled),
    the ``running`` row is an orphan and ``chat_state`` returns ``None`` so the next
    turn starts/resumes instead of reporting a run that is not being driven."""
    run_id = service.start(OWNER, TRIP)  # ``start`` opens the run on the bus
    assert service.chat_state(OWNER, TRIP) == "running"

    service._bus.close(run_id)  # driving turn gone; row still ``running``
    assert service.chat_state(OWNER, TRIP) is None


def test_start_after_a_cancelled_run_resumes_without_spending_the_cap(
    service, factory, daily_limit
) -> None:
    """A cancelled run leaves its row ``running`` and releases its bus channel
    (``runner.run_trip_research``). The next ``start`` for the trip finds that orphan,
    resumes it (``resumed_from`` set, row flipped to ``interrupted``) and — because a
    resume was already paid for — does not spend another daily-cap slot."""
    run_a = service.start(OWNER, TRIP)  # spends 1 of 2
    service._bus.close(run_a)  # mirror the runner's cancel path: channel released

    run_b = service.start(OWNER, TRIP)  # resumes the orphan, spends nothing
    assert service._resumes.get(run_b) == run_a
    assert _get(factory, run_a).status == "interrupted"

    # Only one real slot was spent, so exactly one more start fits under the cap of 2.
    _complete(factory, run_b)
    _complete(factory, service.start(OWNER, TRIP))
    with pytest.raises(RateLimitError):
        service.start(OWNER, TRIP)


@pytest.mark.parametrize(
    ("rubric_status", "review"),
    [
        ("satisfied", "passed"),
        ("max_iterations_reached", "needs_review"),
        ("failed", "needs_review"),
        ("grader_error", "needs_review"),
        (None, None),
    ],
)
def test_review_maps_the_recorded_grader_verdict(
    service,
    factory,
    rubric_status,
    review,
) -> None:
    from app.repositories.agent_run import AgentRunRepository

    run_id = service.start(OWNER, TRIP)
    _complete(factory, run_id)
    if rubric_status is not None:
        AgentRunRepository(factory).add_steps(
            run_id,
            [
                {
                    "seq": 0,
                    "kind": "node",
                    "node": "rubric",
                    "status": "ok",
                    "meta": {"rubric_status": rubric_status},
                }
            ],
        )

    assert service.review(run_id) == review
    expected_state = "needs_review" if review == "needs_review" else "completed"
    assert service.chat_state(OWNER, TRIP) == expected_state
