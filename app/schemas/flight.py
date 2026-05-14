"""Flight schemas: domain models, search response, and booking request."""

from datetime import datetime

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

    Note: ``total_price`` is client-supplied. In a real system this is a
    security issue (the client could send ``$1``). For the mock it keeps the
    FE simple — they pass back whatever price was shown to the user.
    """

    flight_id: str
    passenger_name: str
    passenger_email: str
    total_price: float
    notes: str | None = None
