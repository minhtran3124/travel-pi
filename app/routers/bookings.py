"""Booking endpoints: list (with search/filter/sort/pagination) and retrieval."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.schemas.booking import Booking, BookingListResponse
from app.schemas.pagination import PaginationDep
from app.services.booking_service import BookingService, get_booking_service

router = APIRouter(prefix="/bookings", tags=["bookings"])

BookingsDep = Annotated[BookingService, Depends(get_booking_service)]


@router.get(
    "",
    response_model=BookingListResponse,
    summary="List bookings with optional search, filter, sort, and pagination",
)
def list_bookings(
    bookings: BookingsDep,
    pagination: PaginationDep,
    q: Annotated[
        str | None,
        Query(
            description="Case-insensitive match on booking ID, customer name, or email"
        ),
    ] = None,
    booking_type: Annotated[
        str | None,
        Query(alias="type", description="Filter by booking type", examples=["flight"]),
    ] = None,
    sort: Annotated[
        str,
        Query(description="created_desc | created_asc | price_desc | price_asc"),
    ] = "created_desc",
) -> BookingListResponse:
    """Return bookings matching the optional filters, sorted, and paginated.

    ``total`` reflects the full match count before pagination.
    Unknown ``type`` or ``sort`` values are ignored.
    """
    page, total = pagination.page_of(
        bookings.query(q=q, booking_type=booking_type, sort=sort)
    )
    return BookingListResponse(
        total=total, limit=pagination.limit, offset=pagination.offset, results=page
    )


@router.get(
    "/{booking_id}",
    response_model=Booking,
    summary="Retrieve a booking by ID",
)
def get_booking(booking_id: str, bookings: BookingsDep) -> Booking:
    """Return a booking by ID, or 404 if it does not exist."""
    return bookings.get(booking_id)
