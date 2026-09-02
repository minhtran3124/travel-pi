"""Tests for the book_flight agent tool (MIN-42).

``book_flight`` takes ``user_id`` via ``InjectedState`` (review-A hardening,
E004); it is passed here in the invoke dict the way the graph injects it from
state (it is hidden from the model-facing schema).
"""

import pytest
from langchain_core.tools import ToolException

OWNER = "u_book_owner"


def test_book_flight_guard_raises_without_confirm(agent_db):
    from app.tools.flight_tools import book_flight

    with pytest.raises(ToolException, match="confirm=true"):
        book_flight.invoke(
            {
                "flight_number": "VN123",
                "origin": "HAN",
                "destination": "SGN",
                "departure_date": "2027-03-15",
                "passenger_name": "Test User",
                "passenger_email": "test@example.com",
                "passenger_phone": "+1 555 000 0000",
                "user_id": OWNER,
            }
        )


def test_book_flight_unknown_flight_raises(agent_db):
    from app.tools.flight_tools import book_flight

    with pytest.raises(ToolException):
        book_flight.invoke(
            {
                "flight_id": "00000000-0000-0000-0000-000000000000",
                "passenger_name": "Test User",
                "passenger_email": "test@example.com",
                "passenger_phone": "+1 555 000 0000",
                "confirm": True,
                "user_id": OWNER,
            }
        )


def test_book_flight_happy_path_returns_booking(agent_db):
    from app.db.engine import get_session_factory
    from app.services.flight_service import FlightService
    from app.tools.flight_tools import book_flight

    # Deterministic seed: HAN->SGN on this date returns >=1 flight.
    with get_session_factory(agent_db)() as s:
        flight = FlightService(s).search_flights("HAN", "SGN", "2027-03-15")[0]
        flight_number = flight.flight_number

    result = book_flight.invoke(
        {
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
    )
    assert result["type"] == "flight"
    assert result["status"] == "confirmed"
    assert result["confirmation_code"]


def test_book_flight_repeated_call_creates_distinct_bookings(agent_db):
    """Two identical book_flight calls create two DISTINCT bookings — the tool
    has no idempotency collapse, matching a REST POST with no Idempotency-Key.
    Guards against re-introducing a content-hash idempotency key, which would
    silently swallow an intentional second booking (and, worse, replay a
    cancelled one) — see the PR #80 deep-review revert."""
    from app.db.engine import get_session_factory
    from app.services.flight_service import FlightService
    from app.tools.flight_tools import book_flight

    with get_session_factory(agent_db)() as s:
        flight_number = (
            FlightService(s).search_flights("HAN", "SGN", "2027-03-15")[0].flight_number
        )

    args = {
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
    first = book_flight.invoke(dict(args))
    second = book_flight.invoke(dict(args))

    assert second["id"] != first["id"]
    assert second["confirmation_code"] != first["confirmation_code"]
