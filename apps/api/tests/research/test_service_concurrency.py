"""B3 — ``ResearchService.start`` serializes concurrent starts for one trip.

The guard is a per-trip transaction-scoped advisory lock taken inside the same
transaction as the run-row insert (mirrors the booking gh-198 lock). Deterministic
rather than a barrier race: A holds the lock while its (uncommitted) run row is
invisible to B; B parks on the lock, observed via a third session polling
``pg_locks`` for one ungranted advisory lock. A negative control patches the lock
to a no-op and shows both starts book a run.

Postgres-only (module-level skip on SQLite, where the lock is a no-op). Never run
under ``-n`` / xdist: the ``pg_locks`` ungranted count of 1 assumes cases run one
at a time. Each case uses a fresh ``uuid4().hex`` owner and trip. The sequential
guard on SQLite is covered by ``tests/research/test_service.py``.

Run it against the throwaway Postgres the booking concurrency suite uses, e.g.:

    docker run -d --rm --name b3-pg -p 55432:5432 \\
      -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test \\
      postgres:17-alpine
    cd apps/api && TEST_DATABASE_URL=postgresql+psycopg://test:test@localhost:55432/test \\
      ../../.venv/bin/python -m pytest tests/research/test_service_concurrency.py -q

(do NOT use ``make test-docker`` — its ``down -v`` tears down the dev stack).
"""

from __future__ import annotations

import contextlib
import os
import threading
import time
from unittest.mock import patch
from uuid import uuid4

import pytest
from app.db.base import Base, _utc_now_iso
from app.db.engine import get_engine, get_session_factory
from app.db.locks import advisory_xact_lock
from app.db.models.agent_run import AgentRun
from app.db.models.trip import Trip
from app.exceptions import ConflictError
from app.repositories.agent_run import AgentRunRepository
from app.research.progress import ProgressBus
from app.research.service import (
    RESEARCH_CHANNEL,
    RESEARCH_KIND,
    ResearchService,
    research_lock_name,
    research_thread_id,
)
from langgraph.store.memory import InMemoryStore
from sqlalchemy import func, select, text

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"),
    reason=(
        "Per-trip advisory-lock serialization is Postgres-only; the default unit "
        "suite runs on SQLite, where the lock is a no-op (sequential guard covered "
        "by tests/research/test_service.py)."
    ),
)

_UNGRANTED_ADVISORY = text(
    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted"
)


def _setup(url: str) -> tuple:
    """Fresh owner + trip on the shared Postgres; returns (factory, owner, trip)."""
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    factory = get_session_factory(url)
    owner, trip = uuid4().hex, uuid4().hex
    with factory() as s:
        s.add(Trip(id=trip, user_id=owner, title="Trip", travelers=2))
        s.commit()
    return factory, owner, trip


def _service(factory) -> ResearchService:
    return ResearchService(
        session_factory=factory,
        store=InMemoryStore(),
        agent=None,
        bus=ProgressBus(),
    )


def _running_count(factory, trip: str) -> int:
    with factory() as s:
        return int(
            s.scalar(
                select(func.count())
                .select_from(AgentRun)
                .where(
                    AgentRun.trip_id == trip,
                    AgentRun.kind == RESEARCH_KIND,
                    AgentRun.status == "running",
                )
            )
            or 0
        )


def _hold_lock_and_row(
    session,
    owner: str,
    trip: str,
    bus: ProgressBus,
) -> None:
    """Simulate a concurrent start mid-transaction: take the per-trip lock and
    flush an (uncommitted) running run row, holding both until the caller commits.
    Like ``start``, the run goes live on the bus before its commit — otherwise the
    waiting start would read the committed row as a dead process's orphan."""
    advisory_xact_lock(session, research_lock_name(owner, trip))
    run_id = uuid4().hex
    bus.open(run_id)
    AgentRunRepository(session).start(
        run_id,
        user_id=owner,
        conversation_id=research_thread_id(owner, trip),
        thread_id=research_thread_id(owner, trip),
        trip_id=trip,
        channel=RESEARCH_CHANNEL,
        kind=RESEARCH_KIND,
        started_at=_utc_now_iso(),
    )  # live mode flushes; the row is uncommitted, invisible to other sessions


def _start_in_thread(service, owner: str, trip: str):
    """(thread, result): B calls ``service.start`` and stashes its outcome."""
    result: dict = {}

    def _run() -> None:
        try:
            result["outcome"] = service.start(owner, trip)
        except Exception as exc:  # noqa: BLE001 - record any outcome for the assertion
            result["outcome"] = exc

    return threading.Thread(target=_run), result


def _close_all(*sessions) -> None:
    for session in sessions:
        if session is None:
            continue
        with contextlib.suppress(Exception):
            session.rollback()
        session.close()


def test_concurrent_start_serializes_to_one_run_and_one_conflict() -> None:
    url = os.environ["TEST_DATABASE_URL"]
    factory, owner, trip = _setup(url)
    service = _service(factory)

    a = factory()
    poll = factory()
    thread, result = _start_in_thread(service, owner, trip)
    try:
        # A holds the lock + an uncommitted running row for this trip.
        _hold_lock_and_row(a, owner, trip, service._bus)
        thread.start()

        # Poll a third session until B is parked on the advisory lock.
        ungranted = 0
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            ungranted = poll.execute(_UNGRANTED_ADVISORY).scalar()
            poll.rollback()  # end the read txn so each poll sees live lock state
            if ungranted == 1:
                break
            time.sleep(0.05)
        alive_while_blocked = thread.is_alive()

        a.commit()  # release the lock; B wakes and sees A's now-committed row
        thread.join(timeout=10)

        assert ungranted == 1  # B parked on exactly one ungranted advisory lock
        assert alive_while_blocked  # ... and was still waiting when observed
        assert not thread.is_alive()  # B finished once A released the lock
        assert isinstance(result["outcome"], ConflictError)
        assert _running_count(factory, trip) == 1  # only A's run booked
    finally:
        _close_all(a, poll)


def test_concurrent_start_without_lock_double_books() -> None:
    """Negative control: patch the lock to a no-op and both starts book a run,
    proving the serialization above depends on the lock."""
    url = os.environ["TEST_DATABASE_URL"]
    factory, owner, trip = _setup(url)
    service = _service(factory)

    a = factory()
    thread, result = _start_in_thread(service, owner, trip)
    try:
        with patch("app.research.service.advisory_xact_lock", return_value=None):
            # A holds an uncommitted running row; with the lock a no-op B never
            # waits and its pre-insert check misses A's uncommitted row.
            _hold_lock_and_row(a, owner, trip, service._bus)
            thread.start()
            thread.join(timeout=5)
            finished_while_a_uncommitted = not thread.is_alive()
            a.commit()

        assert finished_while_a_uncommitted  # B ran to completion, never blocked
        assert isinstance(result["outcome"], str)  # B booked a run (returned run_id)
        assert _running_count(factory, trip) == 2  # both inserts landed
    finally:
        _close_all(a)
