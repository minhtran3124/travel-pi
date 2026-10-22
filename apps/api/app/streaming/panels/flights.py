"""``kind="flights"`` panel — the flights drawer's model."""

from __future__ import annotations

from datetime import datetime

from app.schemas.base import AppBaseModel
from app.schemas.flight import Flight
from app.streaming.panels.base import PanelSpec, register_panel


class FlightsPanelFlight(AppBaseModel):
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
        """Project the tool's flight list into the panel model, preserving its sort order."""
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
