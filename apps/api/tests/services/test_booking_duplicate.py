"""Opt-in duplicate-intent check in ``BookingService`` (gh-194, task 1.1).

These exercise the service directly (no HTTP, no tools). With
``check_duplicate=True`` a second *active* booking by the same owner for the
same flight (row + passengers) or hotel (+ exact dates) raises
``DuplicateBookingError`` and stores no new row; the default ``False`` keeps the
REST create-every-time behaviour. Raising cases are named ``test_*_raises*`` and
non-flag cases ``test_*_not_flagged*`` so SC-1/SC-2 ``-k`` filters select them.
Each test uses a unique owner id so the shared session-scoped DB cannot leak
rows between cases.
"""

from __future__ import annotations

import pytest
from app.exceptions import DuplicateBookingError
from app.schemas.flight import FlightBookingRequest
from app.schemas.hotel import HotelBookingRequest
from app.services.booking_service import BookingService
from app.services.flight_service import FlightService
from app.services.hotel_service import HotelService

# Deterministic seeded inventory (mirrors tests/tools/test_booking_idempotency_tools.py).
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


def _hotel_request(
    hotel_id: str, *, check_in: str = HOTEL_CHECK_IN, check_out: str = HOTEL_CHECK_OUT
) -> HotelBookingRequest:
    return HotelBookingRequest(
        hotel_id=hotel_id,
        check_in=check_in,
        check_out=check_out,
        rooms=1,
        adults=2,
        children=0,
        guest_name="Test User",
        guest_email="test@example.com",
        guest_phone="+1 555 000 0000",
    )


# ---------------------------------------------------------------------------
# SC-1 — raising cases
# ---------------------------------------------------------------------------


def test_book_flight_duplicate_raises(service):
    owner = "u_dup_flight_raise"
    flight = _flight(service._session)
    first = service.book_flight(_flight_request(flight), user_id=owner)

    with pytest.raises(DuplicateBookingError) as exc:
        service.book_flight(
            _flight_request(flight), user_id=owner, check_duplicate=True
        )

    # Names the existing booking and stores no new row.
    assert exc.value.existing.id == first.id
    assert first.confirmation_code in exc.value.detail
    assert exc.value.hint is not None and "allow_duplicate" in exc.value.hint
    assert len(service.list_all(user_id=owner)) == 1


def test_book_hotel_duplicate_raises(service):
    owner = "u_dup_hotel_raise"
    hotel_id = _hotel_id(service._session)
    first = service.book_hotel(_hotel_request(hotel_id), user_id=owner)

    with pytest.raises(DuplicateBookingError) as exc:
        service.book_hotel(
            _hotel_request(hotel_id), user_id=owner, check_duplicate=True
        )

    assert exc.value.existing.id == first.id
    assert first.confirmation_code in exc.value.detail
    assert len(service.list_all(user_id=owner)) == 1


# ---------------------------------------------------------------------------
# SC-2 — not-flagged cases
# ---------------------------------------------------------------------------


def test_cancelled_flight_not_flagged(service):
    owner = "u_dup_flight_cancelled"
    flight = _flight(service._session)
    first = service.book_flight(_flight_request(flight), user_id=owner)
    service.cancel(first.id, user_id=owner)

    # A cancelled booking never counts, so re-booking is allowed.
    second = service.book_flight(
        _flight_request(flight), user_id=owner, check_duplicate=True
    )
    assert second.id != first.id


def test_different_passengers_not_flagged(service):
    owner = "u_dup_flight_pax"
    flight = _flight(service._session)
    first = service.book_flight(
        _flight_request(flight, passengers=1), user_id=owner
    )
    second = service.book_flight(
        _flight_request(flight, passengers=2), user_id=owner, check_duplicate=True
    )
    assert second.id != first.id


def test_different_hotel_dates_not_flagged(service):
    owner = "u_dup_hotel_dates"
    hotel_id = _hotel_id(service._session)
    first = service.book_hotel(_hotel_request(hotel_id), user_id=owner)
    second = service.book_hotel(
        _hotel_request(hotel_id, check_in="2027-05-01", check_out="2027-05-04"),
        user_id=owner,
        check_duplicate=True,
    )
    assert second.id != first.id


def test_another_owner_not_flagged(service):
    owner_a = "u_dup_owner_a"
    owner_b = "u_dup_owner_b"
    flight = _flight(service._session)
    service.book_flight(_flight_request(flight), user_id=owner_a)

    # A different owner's identical booking is not a duplicate of owner A's.
    booking_b = service.book_flight(
        _flight_request(flight), user_id=owner_b, check_duplicate=True
    )
    assert len(service.list_all(user_id=owner_b)) == 1
    assert booking_b.id is not None


def test_check_duplicate_false_not_flagged(service):
    owner = "u_dup_flag_off"
    flight = _flight(service._session)
    first = service.book_flight(_flight_request(flight), user_id=owner)
    # Default False (the REST path) still creates a second row.
    second = service.book_flight(_flight_request(flight), user_id=owner)
    assert second.id != first.id
    assert len(service.list_all(user_id=owner)) == 2
