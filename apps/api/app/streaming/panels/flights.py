"""``kind="flights"`` panel — the flights drawer's model."""

from __future__ import annotations

from datetime import datetime

from app.schemas.base import AppBaseModel
from app.schemas.flight import Flight
from app.streaming.panels.base import PanelSpec, register_panel


class FlightsPanelFlight(AppBaseModel):
    """One flight row in a ``kind="flights"`` panel."""

    id: str
    flight_number: str
    airline_name: str
    airline_code: str
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    duration_minutes: int
    stops: int
    seats_available: int
    price: float
    currency: str


class FlightsPanel(AppBaseModel):
    """``data`` payload for a ``kind="flights"`` panel — the flights drawer's model."""

    origin: str
    destination: str
    departure_date: str
    results_count: int
    cheapest_price: float
    flights: list[FlightsPanelFlight]

    @classmethod
    def from_flights(
        cls, origin: str, destination: str, departure_date: str, flights: list[Flight]
    ) -> FlightsPanel:
        """Project the tool's (non-empty) flight list into the panel render model.

        Order is preserved (the tool already applied the requested ``sort``).

        :param origin: Origin code echoed into the header.
        :param destination: Destination code echoed into the header.
        :param departure_date: Departure date echoed into the header.
        :param flights: The non-empty flight list from ``FlightService.search_flights``.
        :return: The flights panel render model.
        """
        return cls(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            results_count=len(flights),
            cheapest_price=min(f.price for f in flights),
            flights=[
                FlightsPanelFlight(
                    id=f.id,
                    flight_number=f.flight_number,
                    airline_name=f.airline.name,
                    airline_code=f.airline.code,
                    origin=f.origin,
                    destination=f.destination,
                    departure_time=f.departure_time,
                    arrival_time=f.arrival_time,
                    duration_minutes=f.duration_minutes,
                    stops=f.stops,
                    seats_available=f.seats_available,
                    price=f.price,
                    currency=f.currency,
                )
                for f in flights
            ],
        )


register_panel(PanelSpec(kind="flights"))
