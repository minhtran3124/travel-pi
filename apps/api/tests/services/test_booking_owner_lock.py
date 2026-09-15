"""Per-owner advisory lock around the duplicate check + insert (gh-198).

Task 1.1 unit tests. The duplicate-intent check (gh-194) reads
``list_active_by_reference`` and then inserts; without serialization two
concurrent requests by the same owner can both pass the check and both insert.
``BookingService`` now takes a per-owner Postgres advisory transaction lock at
the top of each ``if check_duplicate:`` block so the check + insert is
serialized per owner. These tests prove the lock is *called* at the right
points (spied), that the helper's mode guards hold, and that the lock key is
stable and within signed int64. Concurrency itself is proven on Postgres in
tests/api (Task 2.1).

The lock is only taken when ``check_duplicate=True``; it is skipped on an
idempotency replay (the request short-circuits before the check). Each test
uses a unique owner id (``uuid4().hex``) so the shared session-scoped SQLite DB
cannot leak rows — and idempotency keys are derived from the owner because that
index is global across users.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from app.db.engine import get_session_factory
from app.repositories.booking import BookingRepository, _owner_lock_key
from app.schemas.flight import FlightBookingRequest
from app.schemas.hotel import HotelBookingRequest
from app.services.booking_service import BookingService
from app.services.flight_service import FlightService
from app.services.hotel_service import HotelService

# Deterministic seeded inventory (mirrors tests/services/test_booking_duplicate.py).
FLIGHT_ROUTE = ("HAN", "SGN", "2027-03-15")
HOTEL_CITY = "Da Nang"
HOTEL_CHECK_IN = "2027-04-10"
HOTEL_CHECK_OUT = "2027-04-14"


@pytest.fixture()
def service(seeded_session) -> BookingService:
    """A ``BookingService`` bound to a seeded session (reference data present)."""
    return BookingService(seeded_session)


def _flight(session) -> object:
    origin, destination, date = FLIGHT_ROUTE
    return FlightService(session).search_flights(origin, destination, date)[0]


def _hotel_id(session) -> str:
    _, results = HotelService(session).check_availability(
        HOTEL_CITY, HOTEL_CHECK_IN, HOTEL_CHECK_OUT, rooms=1, adults=2, children=0
    )
    return next(h for h in results if h.available).id


def _flight_request(flight, *, passengers: int = 1) -> FlightBookingRequest:
    return FlightBookingRequest(
        flight_id=flight.id,
        passengers=passengers,
        passenger_name="Test User",
        passenger_email="test@example.com",
        passenger_phone="+1 555 000 0000",
    )


def _hotel_request(hotel_id: str) -> HotelBookingRequest:
    return HotelBookingRequest(
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


# ---------------------------------------------------------------------------
# Lock is called at the right points (spy on the repo method)
# ---------------------------------------------------------------------------


def test_book_flight_check_duplicate_locks_owner_once(service):
    owner = uuid4().hex
    flight = _flight(service._session)
    with patch.object(BookingRepository, "lock_owner_bookings", autospec=True) as spy:
        service.book_flight(
            _flight_request(flight), user_id=owner, check_duplicate=True
        )
    assert spy.call_count == 1
    assert spy.call_args.args[1] == owner


def test_book_hotel_check_duplicate_locks_owner_once(service):
    owner = uuid4().hex
    hotel_id = _hotel_id(service._session)
    with patch.object(BookingRepository, "lock_owner_bookings", autospec=True) as spy:
        service.book_hotel(
            _hotel_request(hotel_id), user_id=owner, check_duplicate=True
        )
    assert spy.call_count == 1
    assert spy.call_args.args[1] == owner


def test_book_flight_no_check_does_not_lock(service):
    owner = uuid4().hex
    flight = _flight(service._session)
    with patch.object(BookingRepository, "lock_owner_bookings", autospec=True) as spy:
        service.book_flight(_flight_request(flight), user_id=owner)
    assert spy.call_count == 0


def test_book_hotel_no_check_does_not_lock(service):
    owner = uuid4().hex
    hotel_id = _hotel_id(service._session)
    with patch.object(BookingRepository, "lock_owner_bookings", autospec=True) as spy:
        service.book_hotel(_hotel_request(hotel_id), user_id=owner)
    assert spy.call_count == 0


def test_idempotency_replay_does_not_lock(service):
    owner = uuid4().hex
    key = f"k-{owner}"
    flight = _flight(service._session)
    # First call stores the row (no spy). The replay must short-circuit before
    # the duplicate check, so the lock is never taken on the second call.
    service.book_flight(
        _flight_request(flight),
        user_id=owner,
        idempotency_key=key,
        check_duplicate=True,
    )
    with patch.object(BookingRepository, "lock_owner_bookings", autospec=True) as spy:
        replay = service.book_flight(
            _flight_request(flight),
            user_id=owner,
            idempotency_key=key,
            check_duplicate=True,
        )
    assert spy.call_count == 0
    assert len(service.list_all(user_id=owner)) == 1
    assert replay.id is not None


# ---------------------------------------------------------------------------
# Helper mode guards
# ---------------------------------------------------------------------------


def test_lock_owner_bookings_factory_mode_raises(tmp_db):
    repo = BookingRepository(get_session_factory(tmp_db))
    with pytest.raises(RuntimeError):
        repo.lock_owner_bookings("u")


def test_lock_owner_bookings_sqlite_is_noop(seeded_session):
    assert BookingRepository(seeded_session).lock_owner_bookings("u") is None


# ---------------------------------------------------------------------------
# Lock key
# ---------------------------------------------------------------------------


def test_owner_lock_key_stable():
    assert _owner_lock_key("a") == _owner_lock_key("a")


def test_owner_lock_key_distinct():
    assert _owner_lock_key("a") != _owner_lock_key("b")


def test_owner_lock_key_within_signed_int64():
    for uid in ("a", "b", uuid4().hex):
        key = _owner_lock_key(uid)
        assert -(2**63) <= key < 2**63
