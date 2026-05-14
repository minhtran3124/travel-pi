"""Flight endpoints: search, detail, and booking."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.exceptions import NotFoundError
from app.schemas.booking import Booking
from app.schemas.flight import (
    Flight,
    FlightBookingRequest,
    FlightSearchInfo,
    FlightSearchResponse,
)
from app.services import flight_service
from app.services.booking_service import BookingService, get_booking_service

router = APIRouter(prefix="/flights", tags=["flights"])

BookingsDep = Annotated[BookingService, Depends(get_booking_service)]


# Note: declare "/search" before "/{flight_id}" so it is not captured as an ID.
@router.get(
    "/search",
    response_model=FlightSearchResponse,
    summary="Search flights for a route, with optional round-trip, filters, and sort",
)
def search_flights(
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
        Query(description="Passenger count; echoed back, does not affect results"),
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
        Query(ge=0, description="Only flights at or below this price (USD)"),
    ] = None,
    max_stops: Annotated[
        int | None,
        Query(ge=0, description="Only flights with at most this many stops"),
    ] = None,
    sort: Annotated[
        str,
        Query(
            description=(
                "Sort order: departure_asc (default) | departure_desc | "
                "price_asc | price_desc | duration_asc | duration_desc"
            )
        ),
    ] = "departure_asc",
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
        flights = flight_service.search_flights(
            origin,
            destination,
            departure_date,
            airline=airline_upper,
            max_price=max_price,
            max_stops=max_stops,
            sort=sort,
        )
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid departure_date; expected format YYYY-MM-DD",
        ) from exc

    return_flights: list | None = None
    if return_date is not None:
        try:
            return_flights = flight_service.search_flights(
                destination,
                origin,
                return_date,
                airline=airline_upper,
                max_price=max_price,
                max_stops=max_stops,
                sort=sort,
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
            sort=sort,
        ),
        results=flights,
        return_count=len(return_flights) if return_flights is not None else None,
        return_results=return_flights,
    )


@router.get(
    "/{flight_id}",
    response_model=Flight,
    summary="Get a single flight by ID",
)
def get_flight(flight_id: str) -> Flight:
    """Return a single flight, or 404 if the ID does not resolve."""
    flight = flight_service.find_flight_by_id(flight_id)
    if flight is None:
        raise NotFoundError("Flight not found")
    return flight


@router.post(
    "/book",
    response_model=Booking,
    summary="Create a flight booking",
)
def book_flight(request: FlightBookingRequest, bookings: BookingsDep) -> Booking:
    """Create a flight booking and store it in memory."""
    return bookings.book_flight(request)
