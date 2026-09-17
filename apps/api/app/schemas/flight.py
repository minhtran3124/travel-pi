"""Flight schemas: domain models, search response, and booking request."""

from datetime import datetime

from pydantic import ConfigDict, EmailStr, Field, field_validator, model_validator

from app.schemas.base import AppBaseModel


class Airline(AppBaseModel):
    """An airline operating a flight."""

    code: str = Field(
        description="2-letter IATA airline code, uppercase.",
        examples=["VN", "TG", "SQ"],
    )
    name: str = Field(
        description="Marketing name of the airline.",
        examples=["Vietnam Airlines", "Thai Airways"],
    )


class Flight(AppBaseModel):
    """A single (deterministically generated) flight."""

    id: str = Field(
        description=(
            "Stable flight identifier with pattern "
            "'FL_<ORIGIN>_<DEST>_<YYYYMMDD>_<INDEX>'. Pass this back to "
            "GET /flights/{flight_id} to refetch the same flight."
        ),
        examples=["FL_DAD_SGN_20260601_03"],
    )
    airline: Airline
    flight_number: str = Field(
        description=(
            "Carrier code + number as printed on the boarding pass. The "
            "same number is reused on other days/routes; identify a "
            "specific leg with flight_number + origin + destination + "
            "departure_date."
        ),
        examples=["VN123"],
    )
    origin: str = Field(
        description="3-letter IATA code for the departure airport, uppercase.",
        examples=["DAD"],
    )
    destination: str = Field(
        description="3-letter IATA code for the arrival airport, uppercase.",
        examples=["SGN"],
    )
    departure_time: datetime = Field(
        description="Scheduled departure time, ISO 8601 (local airport time)."
    )
    arrival_time: datetime = Field(
        description="Scheduled arrival time, ISO 8601 (local airport time)."
    )
    duration_minutes: int = Field(
        description="Total elapsed flight time in minutes (door-to-door).",
        examples=[120],
    )
    price: float = Field(
        description="Total fare for one adult in `currency`.", examples=[245.0]
    )
    currency: str = Field(
        default="USD", description="ISO 4217 currency code.", examples=["USD"]
    )
    seats_available: int = Field(
        description="Approximate seats left on this flight at search time.",
        examples=[12],
    )
    stops: int = Field(
        default=0,
        description="Number of intermediate stops (0 = nonstop).",
        examples=[0, 1],
    )


class FlightSearchInfo(AppBaseModel):
    """Echo of the flight search query, returned alongside the results."""

    origin: str = Field(
        description="IATA origin code that was queried.", examples=["DAD"]
    )
    destination: str = Field(
        description="IATA destination code that was queried.", examples=["SGN"]
    )
    departure_date: str = Field(
        description="Departure date the search was run for (YYYY-MM-DD).",
        examples=["2026-06-01"],
    )
    adults: int = Field(description="Number of adult passengers.", examples=[1])
    return_date: str | None = Field(
        default=None,
        description="Set when the search was a round-trip (YYYY-MM-DD).",
        examples=["2026-06-08"],
    )
    airline: str | None = Field(
        default=None,
        description="Applied airline-code filter, if any.",
        examples=["VN"],
    )
    max_price: float | None = Field(
        default=None, description="Applied max-price filter, if any."
    )
    max_stops: int | None = Field(
        default=None, description="Applied max-stops filter, if any."
    )
    sort: str = Field(
        default="departure_asc",
        description=(
            "Sort key applied to the results. One of: "
            "'departure_asc', 'departure_desc', 'price_asc', "
            "'price_desc', 'duration_asc', 'duration_desc'."
        ),
        examples=["price_asc"],
    )


class FlightSearchResponse(AppBaseModel):
    """Response body for ``GET /flights/search``."""

    count: int = Field(description="Number of outbound flights returned.")
    search: FlightSearchInfo
    results: list[Flight]
    return_count: int | None = Field(
        default=None,
        description="Number of return flights (round-trip search only).",
    )
    return_results: list[Flight] | None = Field(
        default=None,
        description="Return-leg flights (destination → origin on return_date).",
    )


class FlightBookingRequest(AppBaseModel):
    """Request body for ``POST /flights/book`` — identify the flight by ``flight_id`` OR the flight_number+origin+destination+departure_date quad (exactly one); fare is server-side."""

    flight_id: str | None = Field(
        default=None,
        description=(
            "The `id` of a flight from a /flights/search result. Provide this "
            "OR the flight_number + origin + destination + departure_date set, "
            "not both."
        ),
        examples=["c0a8011e-5b2e-5f7a-9c3d-1f2e3a4b5c6d"],
    )
    flight_number: str | None = Field(
        default=None,
        description=(
            "Carrier code + number, case-insensitive. 'VN123' and 'VN 123' both "
            "work. Required (with origin/destination/departure_date) when "
            "flight_id is not given."
        ),
        examples=["VN123"],
    )
    origin: str | None = Field(
        default=None, description="3-letter IATA origin code.", examples=["DAD"]
    )
    destination: str | None = Field(
        default=None, description="3-letter IATA destination code.", examples=["SGN"]
    )
    departure_date: str | None = Field(
        default=None,
        description="Departure date in YYYY-MM-DD.",
        examples=["2026-06-01"],
    )
    passengers: int = Field(default=1, ge=1, description="Number of seats to book.")
    passenger_name: str = Field(
        description="Full name as printed on the passenger's ID/passport.",
        examples=["Nguyen Van A"],
    )
    passenger_email: EmailStr = Field(
        description="Contact email for the itinerary and e-ticket.",
        examples=["nguyen.a@example.com"],
    )
    passenger_phone: str = Field(
        description="Contact phone for airline notifications (delays, gate).",
        examples=["+84 901 234 567"],
    )
    notes: str | None = Field(
        default=None,
        description=(
            "Free-form note for the airline — e.g. seat preference, meal "
            "request. Optional."
        ),
        examples=["Window seat preferred"],
    )
    trip_id: str | None = Field(
        default=None,
        description=(
            "Attach this booking to a trip you own (from POST /trips). "
            "Optional; a trip_id you do not own is refused with 404."
        ),
    )

    @field_validator("departure_date")
    @classmethod
    def _valid_departure_date(cls, value: str | None) -> str | None:
        """Reject a malformed date at the schema boundary → 422 (else the lookup returns a misleading 404); None defers to the identifier-mode check."""
        if value is None:
            return value
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("expected date in YYYY-MM-DD format") from exc
        return value

    @model_validator(mode="after")
    def _exactly_one_identifier(self) -> "FlightBookingRequest":
        """Require exactly one flight-identifier mode (flight_id, or the full quad) → 422 otherwise."""
        has_id = bool(self.flight_id)
        quad = (self.flight_number, self.origin, self.destination, self.departure_date)
        has_full_quad = all(quad)

        if has_id and any(quad):
            raise ValueError(
                "provide flight_id OR flight_number+origin+destination+"
                "departure_date, not both"
            )
        if not has_id and not has_full_quad:
            raise ValueError(
                "identify the flight with flight_id, or with flight_number + "
                "origin + destination + departure_date"
            )
        return self

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "flight_id": "c0a8011e-5b2e-5f7a-9c3d-1f2e3a4b5c6d",
                    "passenger_name": "Nguyen Van A",
                    "passenger_email": "nguyen.a@example.com",
                    "passenger_phone": "+84 901 234 567",
                    "notes": "Window seat preferred",
                },
                {
                    "flight_number": "VN123",
                    "origin": "DAD",
                    "destination": "SGN",
                    "departure_date": "2026-06-01",
                    "passenger_name": "Nguyen Van A",
                    "passenger_email": "nguyen.a@example.com",
                    "passenger_phone": "+84 901 234 567",
                    "notes": "Window seat preferred",
                },
            ]
        }
    )
