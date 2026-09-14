"""Duplicate-intent warning on the agent book tools (gh-194, task 2.1).

``book_flight`` / ``book_hotel`` opt into ``BookingService``'s duplicate check
(``check_duplicate=not allow_duplicate``). A genuinely new turn re-booking the
identical active flight/hotel for the same owner must surface a ``ToolException``
that names the existing booking's confirmation code and points at
``allow_duplicate`` — and create no new row. Passing ``allow_duplicate=True``
(the override the model sets only after the traveller confirms) books a second
row. The override is model-visible; injected plumbing stays hidden.

These call the tools directly (no thread/turn context) so idempotency replay is
out of the picture and the duplicate check is what's under test.
"""

from __future__ import annotations

import pytest
from app.db.engine import get_session_factory
from app.services.booking_service import BookingService
from langchain_core.tools import ToolException

OWNER = "u_dup_owner"


def _flight_number(url: str) -> str:
    from app.services.flight_service import FlightService

    with get_session_factory(url)() as s:
        return (
            FlightService(s).search_flights("HAN", "SGN", "2027-03-15")[0].flight_number
        )


def _hotel_id(url: str) -> str:
    from app.services.hotel_service import HotelService

    with get_session_factory(url)() as s:
        _, results = HotelService(s).check_availability(
            "Da Nang", "2027-04-10", "2027-04-14", rooms=1, adults=2, children=0
        )
        return next(h for h in results if h.available).id


def _flight_args(flight_number: str) -> dict:
    return {
        "flight_number": flight_number,
        "origin": "HAN",
        "destination": "SGN",
        "departure_date": "2027-03-15",
        "passenger_name": "Test User",
        "passenger_email": "test@example.com",
        "passenger_phone": "+1 555 000 0000",
        "confirm": True,
        "user_id": OWNER,
    }


def _hotel_args(hotel_id: str) -> dict:
    return {
        "hotel_id": hotel_id,
        "check_in": "2027-04-10",
        "check_out": "2027-04-14",
        "rooms": 1,
        "adults": 2,
        "children": 0,
        "guest_name": "Test User",
        "guest_email": "test@example.com",
        "guest_phone": "+1 555 000 0000",
        "confirm": True,
        "user_id": OWNER,
    }


def _rows(url: str) -> int:
    with get_session_factory(url)() as s:
        return len(BookingService(s).list_all(user_id=OWNER))


# ---------------------------------------------------------------------------
# Flight: new-turn duplicate -> ToolException naming the code + allow_duplicate
# ---------------------------------------------------------------------------


def test_book_flight_duplicate_raises_and_creates_no_row(agent_db):
    from app.tools.flight_tools import book_flight

    args = _flight_args(_flight_number(agent_db))
    first = book_flight.invoke(dict(args))

    with pytest.raises(ToolException) as excinfo:
        book_flight.invoke(dict(args))

    message = str(excinfo.value)
    assert first["confirmation_code"] in message
    assert "allow_duplicate" in message
    # The blocked second attempt must not have persisted anything.
    assert _rows(agent_db) == 1


def test_book_flight_allow_duplicate_books_second_row(agent_db):
    from app.tools.flight_tools import book_flight

    args = _flight_args(_flight_number(agent_db))
    first = book_flight.invoke(dict(args))
    second = book_flight.invoke({**args, "allow_duplicate": True})

    assert second["id"] != first["id"]
    assert _rows(agent_db) == 2


# ---------------------------------------------------------------------------
# Hotel: same shape
# ---------------------------------------------------------------------------


def test_book_hotel_duplicate_raises_and_creates_no_row(agent_db):
    from app.tools.hotel_tools import book_hotel

    args = _hotel_args(_hotel_id(agent_db))
    first = book_hotel.invoke(dict(args))

    with pytest.raises(ToolException) as excinfo:
        book_hotel.invoke(dict(args))

    message = str(excinfo.value)
    assert first["confirmation_code"] in message
    assert "allow_duplicate" in message
    assert _rows(agent_db) == 1


def test_book_hotel_allow_duplicate_books_second_row(agent_db):
    from app.tools.hotel_tools import book_hotel

    args = _hotel_args(_hotel_id(agent_db))
    first = book_hotel.invoke(dict(args))
    second = book_hotel.invoke({**args, "allow_duplicate": True})

    assert second["id"] != first["id"]
    assert _rows(agent_db) == 2


# ---------------------------------------------------------------------------
# Schema: allow_duplicate is model-visible, injected plumbing stays hidden
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tool_name", ["book_flight", "book_hotel"])
def test_allow_duplicate_in_model_schema_injected_hidden(tool_name):
    from app.tools.flight_tools import book_flight
    from app.tools.hotel_tools import book_hotel

    tool = {"book_flight": book_flight, "book_hotel": book_hotel}[tool_name]
    model_fields = tool.tool_call_schema.model_fields
    assert "allow_duplicate" in model_fields
    for hidden in ("user_id", "trip_id", "messages", "config"):
        assert hidden not in model_fields
