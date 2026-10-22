"""Opt-in duplicate-intent check in ``BookingService``: with ``check_duplicate=True`` a second active booking by the same owner for the same flight or hotel raises ``DuplicateBookingError`` and stores no new row; the default ``False`` keeps the REST create-every-time behaviour. Each test uses a unique owner id so the shared session-scoped DB cannot leak rows between cases."""

from __future__ import annotations

import pytest
from app.exceptions import ConflictError, DuplicateBookingError
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
    hotel_id: str,
    *,
    check_in: str = HOTEL_CHECK_IN,
    check_out: str = HOTEL_CHECK_OUT,
    rooms: int = 1,
) -> HotelBookingRequest:
    return HotelBookingRequest(
        hotel_id=hotel_id,
        check_in=check_in,
        check_out=check_out,
        rooms=rooms,
        adults=2,
        children=0,
        guest_name="Test User",
        guest_email="test@example.com",
        guest_phone="+1 555 000 0000",
    )


def test_book_flight_duplicate_raises(service):
    owner = "u_dup_flight_raise"
    flight = _flight(service._session)
    first = service.book_flight(_flight_request(flight), user_id=owner)

    with pytest.raises(DuplicateBookingError) as exc:
        service.book_flight(
            _flight_request(flight), user_id=owner, check_duplicate=True
        )

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
    assert exc.value.hint is not None and "allow_duplicate" in exc.value.hint
    assert len(service.list_all(user_id=owner)) == 1


def test_hotel_unpadded_dates_raises(service):
    """Unpadded request dates ("2027-4-10") must still match a padded existing
    booking ("2027-04-10"): the check compares parsed dates, not raw strings."""
    owner = "u_dup_hotel_unpadded"
    hotel_id = _hotel_id(service._session)
    first = service.book_hotel(_hotel_request(hotel_id), user_id=owner)

    with pytest.raises(DuplicateBookingError) as exc:
        service.book_hotel(
            _hotel_request(hotel_id, check_in="2027-4-10", check_out="2027-4-14"),
            user_id=owner,
            check_duplicate=True,
        )

    assert exc.value.existing.id == first.id
    assert len(service.list_all(user_id=owner)) == 1


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
    first = service.book_flight(_flight_request(flight, passengers=1), user_id=owner)
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


def test_cancelled_hotel_not_flagged(service):
    owner = "u_dup_hotel_cancelled"
    hotel_id = _hotel_id(service._session)
    first = service.book_hotel(_hotel_request(hotel_id), user_id=owner)
    service.cancel(first.id, user_id=owner)

    # A cancelled booking never counts, so re-booking the same dates is allowed.
    second = service.book_hotel(
        _hotel_request(hotel_id), user_id=owner, check_duplicate=True
    )
    assert second.id != first.id


def test_another_owner_hotel_not_flagged(service):
    owner_a = "u_dup_hotel_owner_a"
    owner_b = "u_dup_hotel_owner_b"
    hotel_id = _hotel_id(service._session)
    service.book_hotel(_hotel_request(hotel_id), user_id=owner_a)

    # A different owner's identical hotel booking is not a duplicate of A's.
    booking_b = service.book_hotel(
        _hotel_request(hotel_id), user_id=owner_b, check_duplicate=True
    )
    assert len(service.list_all(user_id=owner_b)) == 1
    assert booking_b.id is not None


def test_hotel_check_duplicate_false_not_flagged(service):
    owner = "u_dup_hotel_flag_off"
    hotel_id = _hotel_id(service._session)
    first = service.book_hotel(_hotel_request(hotel_id), user_id=owner)
    # Default False (the REST path) still creates a second row.
    second = service.book_hotel(_hotel_request(hotel_id), user_id=owner)
    assert second.id != first.id
    assert len(service.list_all(user_id=owner)) == 2


def test_book_hotel_duplicate_message_uses_existing_details(service):
    """The duplicate message is built from the *existing* row, not the new
    request: it names the matched booking's hotel, dates and party size so the
    traveller can tell which booking is meant."""
    owner = "u_dup_hotel_details"
    hotel_id = _hotel_id(service._session)
    first = service.book_hotel(_hotel_request(hotel_id), user_id=owner)

    with pytest.raises(DuplicateBookingError) as exc:
        service.book_hotel(
            _hotel_request(hotel_id, rooms=3), user_id=owner, check_duplicate=True
        )

    detail = exc.value.detail
    assert first.confirmation_code in detail
    assert first.details.hotel_name in detail
    assert HOTEL_CHECK_IN in detail
    assert HOTEL_CHECK_OUT in detail
    assert "1 room(s)" in detail
    assert "3 room(s)" not in detail
    assert exc.value.existing.id == first.id


def test_book_hotel_sold_out_wins_over_duplicate(service, monkeypatch):
    """A sold-out hotel reports sold-out before the duplicate check: an identical
    active booking plus zero free rooms raises ConflictError, not
    DuplicateBookingError, and inserts no row."""
    owner = "u_dup_hotel_sold_out"
    hotel_id = _hotel_id(service._session)
    service.book_hotel(_hotel_request(hotel_id), user_id=owner)

    from app.services import hotel_service as svc

    real = svc.available_rooms
    monkeypatch.setattr(
        svc,
        "available_rooms",
        lambda hotel, check_in, check_out: (
            0 if hotel.id == hotel_id else real(hotel, check_in, check_out)
        ),
    )

    with pytest.raises(ConflictError) as exc:
        service.book_hotel(
            _hotel_request(hotel_id), user_id=owner, check_duplicate=True
        )
    assert not isinstance(exc.value, DuplicateBookingError)
    assert len(service.list_all(user_id=owner)) == 1


def test_book_flight_all_matches_carries_every_active_duplicate(service):
    """Two active bookings match this flight (older X, newer Z); the error names
    the newest as ``existing`` but carries *both* in ``matches`` so the tool can
    refuse an override flagged against either one."""
    owner = "u_dup_flight_all_matches"
    flight = _flight(service._session)
    older = service.book_flight(_flight_request(flight), user_id=owner)
    newer = service.book_flight(_flight_request(flight), user_id=owner)

    with pytest.raises(DuplicateBookingError) as exc:
        service.book_flight(
            _flight_request(flight), user_id=owner, check_duplicate=True
        )

    assert exc.value.existing.id == newer.id
    assert {b.id for b in exc.value.matches} == {older.id, newer.id}
    assert len(service.list_all(user_id=owner)) == 2


def test_book_hotel_all_matches_carries_every_active_duplicate(service):
    """Two active bookings match this hotel + exact dates (older X, newer Z);
    ``existing`` names the newest, ``matches`` carries both."""
    owner = "u_dup_hotel_all_matches"
    hotel_id = _hotel_id(service._session)
    older = service.book_hotel(_hotel_request(hotel_id), user_id=owner)
    newer = service.book_hotel(_hotel_request(hotel_id), user_id=owner)

    with pytest.raises(DuplicateBookingError) as exc:
        service.book_hotel(
            _hotel_request(hotel_id), user_id=owner, check_duplicate=True
        )

    assert exc.value.existing.id == newer.id
    assert {b.id for b in exc.value.matches} == {older.id, newer.id}
    assert len(service.list_all(user_id=owner)) == 2
