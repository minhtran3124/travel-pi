"""``book_flight`` accepts a model-supplied passenger count (Task 2.1).

Unlike ``user_id``/``trip_id``, ``passengers`` is not injected — the traveller
states it, so the model must be able to pass it. It flows straight into
``FlightBookingRequest.passengers``, which prices and records the booking for
that many seats (Task 1.1).
"""

from app.db.engine import get_session_factory

OWNER = "u_pax_book_owner"


def test_book_flight_with_passengers_prices_and_records_seat_count(agent_db):
    from app.services.flight_service import FlightService
    from app.tools.flight_tools import book_flight

    with get_session_factory(agent_db)() as s:
        flight = FlightService(s).search_flights("HAN", "SGN", "2027-03-15")[0]
        flight_number = flight.flight_number
        fare = flight.price

    result = book_flight.invoke(
        {
            "flight_number": flight_number,
            "origin": "HAN",
            "destination": "SGN",
            "departure_date": "2027-03-15",
            "passenger_name": "Test User",
            "passenger_email": "test@example.com",
            "passenger_phone": "+1 555 000 0000",
            "passengers": 3,
            "confirm": True,
            "user_id": OWNER,
        }
    )
    assert result["details"]["passengers"] == 3
    assert result["total_price"] == fare * 3


def test_book_flight_without_passengers_defaults_to_one_seat(agent_db):
    from app.services.flight_service import FlightService
    from app.tools.flight_tools import book_flight

    with get_session_factory(agent_db)() as s:
        flight = FlightService(s).search_flights("HAN", "SGN", "2027-03-15")[0]
        flight_number = flight.flight_number
        fare = flight.price

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
    assert result["details"]["passengers"] == 1
    assert result["total_price"] == fare
