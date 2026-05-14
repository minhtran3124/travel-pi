"""Hotel endpoints: search, detail, and booking."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.exceptions import NotFoundError
from app.schemas.booking import Booking
from app.schemas.hotel import (
    Hotel,
    HotelBookingRequest,
    HotelListResponse,
    HotelSearchInfo,
    HotelSearchResponse,
)
from app.schemas.pagination import PaginationDep
from app.services import hotel_service
from app.services.booking_service import BookingService, get_booking_service

router = APIRouter(prefix="/hotels", tags=["hotels"])

BookingsDep = Annotated[BookingService, Depends(get_booking_service)]


@router.get(
    "",
    response_model=HotelListResponse,
    summary="List all hotels (paginated)",
)
def list_hotels(pagination: PaginationDep) -> HotelListResponse:
    """Return all seeded hotels with pagination.

    ``total`` is the full count; use ``limit`` and ``offset`` to page.
    """
    page, total = pagination.page_of(hotel_service.list_hotels())
    return HotelListResponse(
        total=total, limit=pagination.limit, offset=pagination.offset, results=page
    )


# Note: declare "/search" before "/{hotel_id}" so it is not captured as an ID.
@router.get(
    "/search",
    response_model=HotelSearchResponse,
    summary="Search hotels by city, date range, and optional filters",
)
def search_hotels(
    pagination: PaginationDep,
    city: Annotated[
        str,
        Query(
            description="City name, case-insensitive exact match", examples=["Da Nang"]
        ),
    ],
    check_in: Annotated[
        str,
        Query(description="Check-in date, YYYY-MM-DD", examples=["2026-06-01"]),
    ],
    check_out: Annotated[
        str,
        Query(description="Check-out date, YYYY-MM-DD", examples=["2026-06-03"]),
    ],
    guests: Annotated[int, Query(description="Guest count; echoed back")] = 1,
    min_stars: Annotated[
        int | None,
        Query(ge=1, le=5, description="Minimum star rating (1–5)"),
    ] = None,
    max_price: Annotated[
        float | None,
        Query(ge=0, description="Maximum price per night (USD)"),
    ] = None,
    amenities: Annotated[
        list[str] | None,
        Query(
            description=(
                "Required amenities (all must match). "
                "Repeat the param for multiple values, e.g. ?amenities=Pool&amenities=Spa"
            ),
            examples=["Pool"],
        ),
    ] = None,
) -> HotelSearchResponse:
    """Return hotels matching the city and optional filters, with pagination.

    ``check_in``, ``check_out``, and ``guests`` are echoed back but do not
    filter results. Unknown cities return ``total: 0`` (not a 404).
    ``total`` reflects the full match count; ``results`` is the current page.
    """
    all_results = hotel_service.search_hotels(
        city, min_stars=min_stars, max_price=max_price, amenities=amenities
    )
    page, total = pagination.page_of(all_results)
    return HotelSearchResponse(
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
        search=HotelSearchInfo(
            city=city,
            check_in=check_in,
            check_out=check_out,
            guests=guests,
            min_stars=min_stars,
            max_price=max_price,
            amenities=amenities,
        ),
        results=page,
    )


@router.get(
    "/{hotel_id}",
    response_model=Hotel,
    summary="Get a single hotel by ID",
)
def get_hotel(hotel_id: str) -> Hotel:
    """Return a single hotel, or 404 if the ID does not exist."""
    hotel = hotel_service.get_hotel(hotel_id)
    if hotel is None:
        raise NotFoundError("Hotel not found")
    return hotel


@router.post(
    "/book",
    response_model=Booking,
    summary="Create a hotel booking",
)
def book_hotel(request: HotelBookingRequest, bookings: BookingsDep) -> Booking:
    """Create a hotel booking. ``total_price`` is computed server-side."""
    return bookings.book_hotel(request)
