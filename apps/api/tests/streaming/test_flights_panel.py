"""FlightsPanel projection (specs/flights-side-panel Task 1.1)."""

from datetime import datetime, timezone

from app.schemas.flight import Airline, Flight
from app.streaming.panels import FlightsPanel


def _flight(fnum: str, price: float, dep_hour: int) -> Flight:
    return Flight(
        id=f"FL-{fnum}",
        airline=Airline(code="VJ", name="VietJet Air"),
        flight_number=fnum,
        origin="HAN",
        destination="SGN",
        departure_time=datetime(2027, 3, 15, dep_hour, 0, tzinfo=timezone.utc),
        arrival_time=datetime(2027, 3, 15, dep_hour + 2, 15, tzinfo=timezone.utc),
        duration_minutes=135,
        price=price,
        currency="USD",
        seats_available=5,
        stops=0,
    )


def test_from_flights_projects_all_fields_and_cheapest():
    flights = [_flight("VJ155", 98.0, 9), _flight("VJ179", 76.0, 20)]
    panel = FlightsPanel.from_flights("HAN", "SGN", "2027-03-15", flights)

    assert panel.origin == "HAN"
    assert panel.destination == "SGN"
    assert panel.departure_date == "2027-03-15"
    assert panel.results_count == 2
    assert panel.cheapest_price == 76.0
    assert [f.flight_number for f in panel.flights] == ["VJ155", "VJ179"]  # order preserved
    first = panel.flights[0]
    assert first.airline_name == "VietJet Air"
    assert first.airline_code == "VJ"
    assert first.price == 98.0 and first.currency == "USD"
    assert first.stops == 0 and first.seats_available == 5
