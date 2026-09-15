"""Deterministic Postgres concurrency proof for the per-owner lock (gh-198, task 2.1).

Task 1.1 added a per-owner Postgres advisory transaction lock
(``BookingRepository.lock_owner_bookings``) at the top of each
``if check_duplicate:`` block so the gh-194 duplicate check + insert is
serialized per owner. The SQLite unit suite (tests/services/test_booking_owner_lock.py)
proves the lock is *called* and that its guards hold, but cannot prove
serialization: SQLite is a no-op. These tests prove it on real Postgres, and are
deterministic rather than a barrier race (which could pass without the lock if A
happens to commit before B checks):

- ``blocks_and_rejects``: session A books with ``check_duplicate=True`` and is
  left uncommitted, holding the lock. B (same owner + item, different idempotency
  key) runs in a thread and parks on the lock — observed via a third session
  polling ``pg_locks`` for one ungranted advisory lock. After A commits, B wakes,
  sees A's row, and raises ``DuplicateBookingError``; exactly one active row
  remains.
- ``without_lock_double_books``: the negative control. With
  ``lock_owner_bookings`` patched to a no-op, B never waits, both inserts
  succeed, and two active rows remain — which is exactly what the lock prevents,
  so it proves the first test depends on the lock.

Postgres-only (module-level skip on SQLite). Never run under ``-n`` / xdist: the
``pg_locks`` ungranted count of 1 assumes cases run one at a time. Each case uses
a fresh ``uuid4().hex`` owner and owner-embedded idempotency keys because
``ix_bookings_idempotency_key`` is unique across ALL users, and the criteria that
reuse one container would otherwise collide on that index instead of the lock.
"""

from __future__ import annotations

import contextlib
import os
import threading
import time
from unittest.mock import patch
from uuid import uuid4

import pytest
from app.db.engine import get_session_factory
from app.enums import BookingType
from app.exceptions import DuplicateBookingError
from app.repositories.booking import BookingRepository
from app.schemas.booking import Booking
from app.schemas.flight import FlightBookingRequest
from app.schemas.hotel import HotelBookingRequest
from app.services.booking_service import BookingService
from app.services.flight_service import FlightService
from app.services.hotel_service import HotelService
from sqlalchemy import text

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql"),
    reason=(
        "Per-owner advisory-lock serialization is Postgres-only; the default "
        "unit suite runs on SQLite, where the lock is a no-op."
    ),
)

# Deterministic seeded inventory (mirrors tests/services/test_booking_duplicate.py).
FLIGHT_ROUTE = ("HAN", "SGN", "2027-03-15")
HOTEL_CITY = "Da Nang"
HOTEL_CHECK_IN = "2027-04-10"
HOTEL_CHECK_OUT = "2027-04-14"

#: One waiting per-owner advisory lock is the signature of B parked behind A.
_UNGRANTED_ADVISORY = text(
    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted"
)


def _flight_scenario(session):
    """Resolve the seeded flight and build the shared booking request."""
    origin, destination, date_ = FLIGHT_ROUTE
    flight = FlightService(session).search_flights(origin, destination, date_)[0]
    request = FlightBookingRequest(
        flight_id=flight.id,
        passengers=1,
        passenger_name="Test User",
        passenger_email="test@example.com",
        passenger_phone="+1 555 000 0000",
    )
    return "book_flight", request, BookingType.FLIGHT.value, flight.id


def _hotel_scenario(session):
    """Resolve the seeded hotel and build the shared booking request."""
    _, results = HotelService(session).check_availability(
        HOTEL_CITY, HOTEL_CHECK_IN, HOTEL_CHECK_OUT, rooms=1, adults=2, children=0
    )
    hotel_id = next(h for h in results if h.available).id
    request = HotelBookingRequest(
        hotel_id=hotel_id,
        check_in=HOTEL_CHECK_IN,
        check_out=HOTEL_CHECK_OUT,
        rooms=1,
        adults=2,
        children=0,
        guest_name="Test User",
        guest_email="test@example.com",
        guest_phone="+1 555 000 0000",
    )
    return "book_hotel", request, BookingType.HOTEL.value, hotel_id


_SCENARIOS = {"flight": _flight_scenario, "hotel": _hotel_scenario}


def _book_in_thread(factory, method, request, owner, key):
    """Build (thread, result) for B: its own session, own idempotency key.

    The thread commits on success and rolls back on failure, then stashes the
    outcome (a ``Booking`` or the raised exception) in ``result["outcome"]`` and
    its session in ``result["session"]`` so the caller can close it.
    """
    result: dict = {}

    def _run():
        session = factory()
        result["session"] = session
        try:
            booking = getattr(BookingService(session), method)(
                request,
                user_id=owner,
                idempotency_key=key,
                check_duplicate=True,
            )
            session.commit()
            result["outcome"] = booking
        except Exception as exc:  # noqa: BLE001 - record any outcome for the assertion
            session.rollback()
            result["outcome"] = exc

    return threading.Thread(target=_run), result


def _close_all(*sessions):
    """Close every session (rolling back any open transaction), best-effort.

    Rolling back here releases a still-held advisory lock if a test failed before
    A committed, so a leaked lock cannot block a later case.
    """
    for session in sessions:
        if session is None:
            continue
        with contextlib.suppress(Exception):
            session.rollback()
        session.close()


@pytest.mark.parametrize("kind", ["flight", "hotel"])
def test_concurrent_duplicate_blocks_and_rejects(tmp_db, seeded_session, kind):
    factory = get_session_factory(tmp_db)
    owner = uuid4().hex
    method, request, booking_type, reference_id = _SCENARIOS[kind](seeded_session)

    a = factory()
    poll = factory()
    thread, result = _book_in_thread(factory, method, request, owner, f"k-b-{owner}")
    try:
        # A takes the per-owner lock and flushes an (uncommitted) row; it holds
        # the transaction-scoped lock until we commit below.
        getattr(BookingService(a), method)(
            request,
            user_id=owner,
            idempotency_key=f"k-a-{owner}",
            check_duplicate=True,
        )
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

        a.commit()  # release the lock; B wakes, sees A's row
        thread.join(timeout=10)

        assert ungranted == 1  # B parked on exactly one ungranted advisory lock
        assert alive_while_blocked  # ... and was still waiting when observed
        assert not thread.is_alive()  # B finished once A released the lock
        assert isinstance(result["outcome"], DuplicateBookingError)
        active = BookingRepository(factory).list_active_by_reference(
            owner, booking_type, reference_id
        )
        assert len(active) == 1
    finally:
        _close_all(a, poll, result.get("session"))


@pytest.mark.parametrize("kind", ["flight", "hotel"])
def test_concurrent_duplicate_without_lock_double_books(tmp_db, seeded_session, kind):
    factory = get_session_factory(tmp_db)
    owner = uuid4().hex
    method, request, booking_type, reference_id = _SCENARIOS[kind](seeded_session)

    a = factory()
    thread, result = _book_in_thread(factory, method, request, owner, f"k-b-{owner}")
    try:
        # Negative control: with the lock a no-op, B never waits on A.
        with patch.object(BookingRepository, "lock_owner_bookings", return_value=None):
            getattr(BookingService(a), method)(
                request,
                user_id=owner,
                idempotency_key=f"k-a-{owner}",
                check_duplicate=True,
            )
            thread.start()
            thread.join(timeout=5)
            finished_while_a_uncommitted = not thread.is_alive()
            a.commit()

        assert finished_while_a_uncommitted  # B ran to completion, never blocked
        assert isinstance(result["outcome"], Booking)  # B produced a booking
        active = BookingRepository(factory).list_active_by_reference(
            owner, booking_type, reference_id
        )
        assert len(active) == 2  # both inserts landed — the lock is what prevents this
    finally:
        _close_all(a, result.get("session"))
