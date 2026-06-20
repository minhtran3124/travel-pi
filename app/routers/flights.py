"""Flight endpoints: search, detail, and booking."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status

from app.enums import FlightSort
from app.exceptions import NotFoundError
from app.schemas.booking import Booking
from app.schemas.error import error_responses
from app.schemas.flight import (
    Flight,
    FlightBookingRequest,
    FlightSearchInfo,
    FlightSearchResponse,
)
from app.services.booking_service import BookingService, get_booking_service
from app.services.flight_service import FlightService, get_flight_service

router = APIRouter(prefix="/flights", tags=["flights"])

BookingsDep = Annotated[BookingService, Depends(get_booking_service)]
FlightDep = Annotated[FlightService, Depends(get_flight_service)]


# Note: declare "/search" before "/{flight_id}" so it is not captured as an ID.
@router.get(
    "/search",
    response_model=FlightSearchResponse,
    summary="Search flights for a route, with optional round-trip, filters, and sort",
    responses=error_responses(422),
)
def search_flights(
    flights_svc: FlightDep,
    origin: Annotated[
        str,
        Query(description="IATA 3-letter code, case-insensitive", examples=["DAD"]),
    ],
    destination: Annotated[
        str,
        Query(description="IATA 3-letter code, case-insensitive", examples=["SGN"]),
    ],
    departure_date: Annotated[
        str,
        Query(description="Departure date, YYYY-MM-DD", examples=["2026-06-01"]),
    ],
    adults: Annotated[
        int,
        Query(
            description="Passenger count; echoed back, does not affect results",
            examples=[1],
        ),
    ] = 1,
    return_date: Annotated[
        str | None,
        Query(
            description=(
                "Return date YYYY-MM-DD. When set, response includes "
                "``return_results`` (destination → origin flights)."
            ),
            examples=["2026-06-08"],
        ),
    ] = None,
    airline: Annotated[
        str | None,
        Query(description="Filter by IATA airline code, e.g. VN", examples=["VN"]),
    ] = None,
    max_price: Annotated[
        float | None,
        Query(
            ge=0,
            description="Only flights at or below this price (USD)",
            examples=[300],
        ),
    ] = None,
    max_stops: Annotated[
        int | None,
        Query(
            ge=0,
            description="Only flights with at most this many stops",
            examples=[0],
        ),
    ] = None,
    sort: Annotated[
        FlightSort,
        Query(
            description="Sort order — Swagger renders the dropdown.",
            examples=["departure_asc"],
        ),
    ] = FlightSort.DEPARTURE_ASC,
) -> FlightSearchResponse:
    """Return up to 5 deterministic mock flights for a route and date.

    When ``return_date`` is supplied, the response also contains
    ``return_results`` — the matching return-leg flights (destination → origin)
    with the same filters applied. Both legs are independently sorted.
    """
    origin = origin.upper()
    destination = destination.upper()
    airline_upper = airline.upper() if airline else None

    try:
        flights = flights_svc.search_flights(
            origin,
            destination,
            departure_date,
            airline=airline_upper,
            max_price=max_price,
            max_stops=max_stops,
            sort=sort.value,
        )
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid departure_date; expected format YYYY-MM-DD",
        ) from exc

    return_flights: list | None = None
    if return_date is not None:
        try:
            return_flights = flights_svc.search_flights(
                destination,
                origin,
                return_date,
                airline=airline_upper,
                max_price=max_price,
                max_stops=max_stops,
                sort=sort.value,
            )
        except ValueError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid return_date; expected format YYYY-MM-DD",
            ) from exc

    return FlightSearchResponse(
        count=len(flights),
        search=FlightSearchInfo(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            adults=adults,
            return_date=return_date,
            airline=airline_upper,
            max_price=max_price,
            max_stops=max_stops,
            sort=sort.value,
        ),
        results=flights,
        return_count=len(return_flights) if return_flights is not None else None,
        return_results=return_flights,
    )


@router.get(
    "/{flight_id}",
    response_model=Flight,
    summary="Get a single flight by ID",
    responses=error_responses(404, 422),
)
def get_flight(
    flights_svc: FlightDep,
    flight_id: Annotated[
        str,
        Path(
            description="Flight UUID returned by /flights/search",
            examples=["7af6f5a4-ce3a-5b24-8f2e-8a0a8b3c2c5a"],
        ),
    ],
) -> Flight:
    """Return a single flight, or 404 if the ID does not resolve."""
    flight = flights_svc.find_flight_by_id(flight_id)
    if flight is None:
        raise NotFoundError(
            f"Flight {flight_id!r} not found",
            hint=(
                "Flight IDs come from GET /flights/search and have the form "
                "'FL_<ORIGIN>_<DEST>_<YYYYMMDD>_<NN>'. Re-run the search "
                "for the same origin/destination/departure_date to get a "
                "valid ID."
            ),
        )
    return flight


@router.post(
    "/book",
    response_model=Booking,
    summary="Create a flight booking",
    responses=error_responses(404, 422),
)
def book_flight(
    request: FlightBookingRequest,
    bookings: BookingsDep,
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            description=(
                "Optional client-supplied key that makes this POST "
                "replay-safe: repeating the request with the same key "
                "returns the original booking instead of creating a "
                "duplicate."
            ),
            examples=["booking-2026-06-01-abc123"],
        ),
    ] = None,
) -> Booking:
    """Create a flight booking, or replay an earlier one for the same key."""
    return bookings.book_flight(request, idempotency_key=idempotency_key)
