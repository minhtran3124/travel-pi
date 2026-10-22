"""Booking endpoints: list (with search/filter/sort/pagination) and retrieval."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.core.auth import CurrentUserDep
from app.enums import BookingSort, BookingType
from app.routers.tags import Tags
from app.schemas.booking import Booking, BookingListResponse
from app.schemas.error import error_responses
from app.schemas.pagination import PaginationDep
from app.services.booking_service import BookingService, get_booking_service

router = APIRouter(
    prefix="/bookings", tags=[Tags.bookings], responses=error_responses(422)
)

BookingsDep = Annotated[BookingService, Depends(get_booking_service)]


@router.get(
    "",
    response_model=BookingListResponse,
    summary="List bookings with optional search, filter, sort, and pagination",
)
def list_bookings(
    bookings: BookingsDep,
    auth_user: CurrentUserDep,
    pagination: PaginationDep,
    q: Annotated[
        str | None,
        Query(
            description="Case-insensitive match on booking ID, confirmation code, customer name, or email",
            examples=["john"],
        ),
    ] = None,
    booking_type: Annotated[
        BookingType | None,
        Query(alias="type", description="Filter by booking type", examples=["flight"]),
    ] = None,
    trip_id: Annotated[
        str | None,
        Query(description="Filter by linked trip id", examples=["t_123"]),
    ] = None,
    sort: Annotated[
        BookingSort,
        Query(
            description="Sort order — Swagger renders the dropdown.",
            examples=["created_desc"],
        ),
    ] = BookingSort.CREATED_DESC,
) -> BookingListResponse:
    """Return bookings matching the optional filters, sorted, and paginated."""
    page, total = pagination.page_of(
        bookings.query(
            user_id=auth_user.id,
            q=q,
            booking_type=booking_type.value if booking_type else None,
            trip_id=trip_id,
            sort=sort.value,
        )
    )
    return BookingListResponse(
        total=total, limit=pagination.limit, offset=pagination.offset, results=page
    )


@router.get(
    "/{booking_id}",
    response_model=Booking,
    summary="Retrieve a booking by UUID or confirmation code",
    responses=error_responses(404),
)
def get_booking(
    bookings: BookingsDep,
    auth_user: CurrentUserDep,
    booking_id: Annotated[
        str,
        Path(
            description="Booking UUID *or* 6-char confirmation code",
            examples=["A2B4C6"],
        ),
    ],
) -> Booking:
    """Return the caller's booking by its UUID *or* friendly confirmation code."""
    return bookings.get(booking_id, user_id=auth_user.id)


@router.post(
    "/{booking_id}/cancel",
    response_model=Booking,
    summary="Cancel a booking by UUID or confirmation code",
    responses=error_responses(404),
)
def cancel_booking(
    bookings: BookingsDep,
    auth_user: CurrentUserDep,
    booking_id: Annotated[
        str,
        Path(
            description="Booking UUID *or* 6-char confirmation code",
            examples=["A2B4C6"],
        ),
    ],
) -> Booking:
    """Cancel the caller's booking (kept and still retrievable); idempotent no-op if already cancelled."""
    return bookings.cancel(booking_id, user_id=auth_user.id)
