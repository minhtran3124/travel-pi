"""Tests for cancel_flight / cancel_hotel agent tools (MIN-42).

The cancel tools take ``user_id`` via ``InjectedState`` (review-A hardening,
E004): they load and cancel scoped to that owner, so the ``user_id`` passed to
the tool must match the owner the booking was created under.
"""

import pytest
from langchain_core.tools import ToolException

OWNER = "u_cancel_owner"


def _book_a_flight(url: str, user_id: str = OWNER) -> str:
    """Arrange a real flight booking for ``user_id``; return its confirmation_code."""
    from app.db.engine import get_session_factory
    from app.schemas.flight import FlightBookingRequest
    from app.services.booking_service import BookingService
    from app.services.flight_service import FlightService

    with get_session_factory(url)() as s:
        flight = FlightService(s).search_flights("HAN", "SGN", "2027-03-15")[0]
        booking = BookingService(s).book_flight(
            FlightBookingRequest(
                flight_number=flight.flight_number,
                origin="HAN",
                destination="SGN",
                departure_date="2027-03-15",
                passenger_name="Test User",
                passenger_email="test@example.com",
                passenger_phone="+1 555 000 0000",
            ),
            user_id=user_id,
        )
        s.commit()
        return booking.confirmation_code


def _book_a_hotel(url: str, user_id: str = OWNER) -> str:
    """Arrange a real hotel booking for ``user_id``; return its confirmation_code."""
    from app.db.engine import get_session_factory
    from app.schemas.hotel import HotelBookingRequest
    from app.services.booking_service import BookingService
    from app.services.hotel_service import HotelService

    with get_session_factory(url)() as s:
        _, results = HotelService(s).check_availability(
            "Da Nang", "2027-04-10", "2027-04-14", rooms=1, adults=2, children=0
        )
        hotel = next((h for h in results if h.available), None)
        assert hotel is not None, "no available Da Nang hotel to arrange the test"
        booking = BookingService(s).book_hotel(
            HotelBookingRequest(
                hotel_id=hotel.id,
                check_in="2027-04-10",
                check_out="2027-04-14",
                rooms=1,
                adults=2,
                children=0,
                guest_name="Test User",
                guest_email="test@example.com",
                guest_phone="+1 555 000 0000",
            ),
            user_id=user_id,
        )
        s.commit()
        return booking.confirmation_code


def test_cancel_flight_happy_path(agent_db):
    from app.tools.booking_tools import cancel_flight

    code = _book_a_flight(agent_db)
    result = cancel_flight.invoke(
        {"booking_id": code, "confirm": True, "user_id": OWNER}
    )
    assert result["type"] == "flight"
    assert result["status"] == "cancelled"


def test_cancel_hotel_happy_path(agent_db):
    from app.tools.booking_tools import cancel_hotel

    code = _book_a_hotel(agent_db)
    result = cancel_hotel.invoke(
        {"booking_id": code, "confirm": True, "user_id": OWNER}
    )
    assert result["type"] == "hotel"
    assert result["status"] == "cancelled"


def test_cancel_flight_other_owner_reads_as_not_found(agent_db):
    """A booking owned by someone else must read as not-found, never cancel (#118)."""
    from app.tools.booking_tools import cancel_flight

    code = _book_a_flight(agent_db, user_id=OWNER)
    with pytest.raises(ToolException, match="not found"):
        cancel_flight.invoke(
            {"booking_id": code, "confirm": True, "user_id": "someone-else"}
        )


def test_cancel_flight_missing_confirm_raises(agent_db):
    from app.tools.booking_tools import cancel_flight

    code = _book_a_flight(agent_db)
    with pytest.raises(ToolException, match="confirm=true"):
        cancel_flight.invoke({"booking_id": code, "user_id": OWNER})


def test_cancel_flight_unknown_id_raises(agent_db):
    from app.tools.booking_tools import cancel_flight

    with pytest.raises(ToolException, match="not found"):
        cancel_flight.invoke(
            {"booking_id": "ZZ9999", "confirm": True, "user_id": OWNER}
        )


def test_cancel_flight_on_hotel_booking_raises_wrong_type(agent_db):
    from app.tools.booking_tools import cancel_flight

    hotel_code = _book_a_hotel(agent_db)
    with pytest.raises(ToolException, match="not a flight booking"):
        cancel_flight.invoke(
            {"booking_id": hotel_code, "confirm": True, "user_id": OWNER}
        )
