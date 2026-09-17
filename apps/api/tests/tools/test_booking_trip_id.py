"""``book_flight`` / ``book_hotel`` thread the graph's active trip into the
booking. ``trip_id`` is injected via ``InjectedState`` and hidden from the
model-facing schema; with no trip in state the tool books with ``trip_id=None``
rather than refusing."""

from app.db.engine import get_session_factory
from app.schemas.trip import TripCreate
from app.services.trip_service import TripService

OWNER = "u_trip_book_owner"


def _create_trip(url: str, user_id: str) -> str:
    with get_session_factory(url)() as s:
        trip = TripService(s, user_id).create_trip(
            TripCreate(title="Trip for booking", city="Da Nang")
        )
        s.commit()
        return trip.id


def test_book_flight_stamps_injected_trip_id(agent_db):
    from app.services.flight_service import FlightService
    from app.tools.flight_tools import book_flight

    trip_id = _create_trip(agent_db, OWNER)
    with get_session_factory(agent_db)() as s:
        flight_number = (
            FlightService(s).search_flights("HAN", "SGN", "2027-03-15")[0].flight_number
        )

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
            "trip_id": trip_id,
        }
    )
    assert result["status"] == "confirmed"
    assert result["trip_id"] == trip_id


def test_book_flight_no_active_trip_books_unattached(agent_db):
    """No trip in state -> trip_id stays None; booking still succeeds."""
    from app.services.flight_service import FlightService
    from app.tools.flight_tools import book_flight

    with get_session_factory(agent_db)() as s:
        flight_number = (
            FlightService(s).search_flights("HAN", "SGN", "2027-03-15")[0].flight_number
        )

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
    assert result["status"] == "confirmed"
    assert result["trip_id"] is None


def test_book_hotel_stamps_injected_trip_id(agent_db):
    from app.services.hotel_service import HotelService
    from app.tools.hotel_tools import book_hotel

    trip_id = _create_trip(agent_db, OWNER)
    with get_session_factory(agent_db)() as s:
        _, results = HotelService(s).check_availability(
            "Da Nang", "2027-04-10", "2027-04-14", rooms=1, adults=2, children=0
        )
        hotel_id = next(h for h in results if h.available).id

    result = book_hotel.invoke(
        {
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
            "trip_id": trip_id,
        }
    )
    assert result["type"] == "hotel"
    assert result["trip_id"] == trip_id


def test_book_hotel_no_active_trip_books_unattached(agent_db):
    """No trip in state -> trip_id stays None; booking still succeeds."""
    from app.services.hotel_service import HotelService
    from app.tools.hotel_tools import book_hotel

    with get_session_factory(agent_db)() as s:
        _, results = HotelService(s).check_availability(
            "Da Nang", "2027-04-10", "2027-04-14", rooms=1, adults=2, children=0
        )
        hotel_id = next(h for h in results if h.available).id

    result = book_hotel.invoke(
        {
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
    )
    assert result["type"] == "hotel"
    assert result["trip_id"] is None


def test_trip_id_hidden_from_model_facing_schema():
    from app.tools.registry import ALL_TOOLS

    for tool_name in ("book_flight", "book_hotel"):
        tool = next(t for t in ALL_TOOLS if t.name == tool_name)
        assert "trip_id" not in tool.tool_call_schema.model_fields
        assert "trip_id" in tool.get_input_schema().model_fields
