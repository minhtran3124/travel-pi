"""Booking endpoints: list (with search/filter/sort/pagination) and retrieval."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.schemas.booking import Booking, BookingListResponse
from app.schemas.error import error_responses
from app.schemas.pagination import PaginationDep
from app.services.booking_service import BookingService, get_booking_service

router = APIRouter(prefix="/bookings", tags=["bookings"])

BookingsDep = Annotated[BookingService, Depends(get_booking_service)]


@router.get(
    "",
    response_model=BookingListResponse,
    summary="List bookings with optional search, filter, sort, and pagination",
    responses=error_responses(422),
)
def list_bookings(
    bookings: BookingsDep,
    pagination: PaginationDep,
    q: Annotated[
        str | None,
        Query(
            description="Case-insensitive match on booking ID, customer name, or email",
            example="john",
        ),
    ] = None,
    booking_type: Annotated[
        str | None,
        Query(alias="type", description="Filter by booking type", example="flight"),
    ] = None,
    sort: Annotated[
        str,
        Query(
            description="created_desc | created_asc | price_desc | price_asc",
            example="created_desc",
        ),
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
    summary="Retrieve a booking by UUID or confirmation code",
    responses=error_responses(404, 422),
)
def get_booking(
    bookings: BookingsDep,
    booking_id: Annotated[
        str,
        Path(
            description="Booking UUID *or* 6-char confirmation code",
            example="A2B4C6",
        ),
    ],
) -> Booking:
    """Return a booking by its UUID *or* its friendly confirmation code.

    Both identifiers are accepted interchangeably; 404 if neither matches.
    """
    return bookings.get(booking_id)


@router.post(
    "/{booking_id}/cancel",
    response_model=Booking,
    summary="Cancel a booking by UUID or confirmation code",
    responses=error_responses(404, 422),
)
def cancel_booking(
    bookings: BookingsDep,
    booking_id: Annotated[
        str,
        Path(
            description="Booking UUID *or* 6-char confirmation code",
            example="A2B4C6",
        ),
    ],
) -> Booking:
    """Cancel a booking and return it with ``status: "cancelled"``.

    Accepts the UUID or the confirmation code. A soft change — the booking
    is kept and still retrievable. Idempotent: cancelling an
    already-cancelled booking is a no-op. 404 if no booking matches.
    """
    return bookings.cancel(booking_id)
