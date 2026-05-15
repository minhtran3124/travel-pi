"""Flight schemas: domain models, search response, and booking request."""

from datetime import datetime

from pydantic import ConfigDict

from app.schemas.base import AppBaseModel


class Airline(AppBaseModel):
    """An airline operating a flight."""

    code: str  # IATA airline code, e.g. "VN"
    name: str  # e.g. "Vietnam Airlines"


class Flight(AppBaseModel):
    """A single (deterministically generated) flight."""

    id: str  # Pattern: FL_{ORIGIN}{DESTINATION}_{YYYYMMDD}_{INDEX}
    airline: Airline
    flight_number: str  # e.g. "VN123"
    origin: str  # IATA 3-letter, uppercase
    destination: str  # IATA 3-letter, uppercase
    departure_time: datetime
    arrival_time: datetime
    duration_minutes: int
    price: float
    currency: str = "USD"
    seats_available: int
    stops: int = 0


class FlightSearchInfo(AppBaseModel):
    """Echo of the flight search query, returned alongside the results."""

    origin: str
    destination: str
    departure_date: str
    adults: int
    return_date: str | None = None  # Set for round-trip searches
    # Optional filters / sort — echoed back so the client knows what was applied.
    airline: str | None = None
    max_price: float | None = None
    max_stops: int | None = None
    sort: str = "departure_asc"


class FlightSearchResponse(AppBaseModel):
    """Response body for ``GET /flights/search``."""

    count: int
    search: FlightSearchInfo
    results: list[Flight]
    # Round-trip: return flights (destination → origin on return_date).
    return_count: int | None = None
    return_results: list[Flight] | None = None


class FlightBookingRequest(AppBaseModel):
    """Request body for ``POST /flights/book``.

    Mirrors what an airline actually collects to issue a ticket: the chosen
    flight plus the passenger's name (as on their ID) and contact details.
    The flight is identified the way an agent or human reads it back from
    search results — the **flight number** (e.g. ``"VN123"``) plus the
    **route and date** that pin which leg it is (the same flight number is
    reused on other days and routes). The fare is *not* sent by the client —
    it is taken server-side from the selected flight, so the price can't be
    tampered with.
    """

    flight_number: str  # e.g. "VN123" — case-insensitive, "VN 123" also accepted
    origin: str  # IATA 3-letter code, e.g. "DAD"
    destination: str  # IATA 3-letter code, e.g. "SGN"
    departure_date: str  # YYYY-MM-DD — the date the flight departs
    passenger_name: str  # Full name as printed on the passenger's ID/passport
    passenger_email: str  # Contact email for the itinerary / e-ticket
    passenger_phone: str  # Contact phone for airline notifications (delays, gate)
    notes: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "flight_number": "VN123",
                "origin": "DAD",
                "destination": "SGN",
                "departure_date": "2026-06-01",
                "passenger_name": "Nguyen Van A",
                "passenger_email": "nguyen.a@example.com",
                "passenger_phone": "+84 901 234 567",
                "notes": "Window seat preferred",
            }
        }
    )
