"""Trip (itinerary) endpoints: create, list, retrieve, amend, cancel.

A trip aggregates a destination, dates, the bookings made for it, and an
itinerary of places — the plan the Travel Planner agent builds up. Trips are
mutable, persisted alongside bookings.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, status

from app.enums import TripStatus
from app.schemas.error import error_responses
from app.schemas.pagination import PaginationDep
from app.schemas.trip import (
    Trip,
    TripCreateRequest,
    TripDetail,
    TripListResponse,
    TripUpdateRequest,
)
from app.services.booking_service import BookingService, get_booking_service
from app.services.trip_service import TripService, get_trip_service

router = APIRouter(prefix="/trips", tags=["trips"])

TripsDep = Annotated[TripService, Depends(get_trip_service)]
BookingsDep = Annotated[BookingService, Depends(get_booking_service)]

_IDEMPOTENCY_HEADER = Header(
    alias="Idempotency-Key",
    description=(
        "Optional client-supplied key that makes this POST replay-safe: "
        "repeating the request with the same key returns the original trip "
        "instead of creating a duplicate."
    ),
    examples=["trip-2026-06-01-abc123"],
)


@router.post(
    "",
    response_model=Trip,
    summary="Create a trip (itinerary)",
    responses=error_responses(404, 422),
)
def create_trip(
    request: TripCreateRequest,
    trips: TripsDep,
    bookings: BookingsDep,
    idempotency_key: Annotated[str | None, _IDEMPOTENCY_HEADER] = None,
) -> Trip:
    """Create a trip, or replay an earlier one for the same key.

    ``destination_city`` is matched fuzzily; any ``booking_ids`` and itinerary
    ``items`` are validated to reference existing bookings/places (404 if
    not). Dates must be valid ``YYYY-MM-DD`` with ``end_date`` on or after
    ``start_date`` (422 otherwise).
    """
    try:
        return trips.create(
            request, booking_service=bookings, idempotency_key=idempotency_key
        )
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get(
    "",
    response_model=TripListResponse,
    summary="List trips with optional search, filter, and pagination",
    responses=error_responses(422),
)
def list_trips(
    trips: TripsDep,
    pagination: PaginationDep,
    q: Annotated[
        str | None,
        Query(
            description="Case-insensitive match on trip ID, code, name, or city",
            examples=["da nang"],
        ),
    ] = None,
    trip_status: Annotated[
        TripStatus | None,
        Query(alias="status", description="Filter by status", examples=["planning"]),
    ] = None,
    destination: Annotated[
        str | None,
        Query(
            description="Filter by destination city (substring)", examples=["Da Nang"]
        ),
    ] = None,
) -> TripListResponse:
    """Return trips matching the optional filters, newest first, paginated.

    ``total`` reflects the full match count before pagination.
    """
    page, total = pagination.page_of(
        trips.query(
            q=q,
            status=trip_status.value if trip_status else None,
            destination=destination,
        )
    )
    return TripListResponse(
        total=total, limit=pagination.limit, offset=pagination.offset, results=page
    )


@router.get(
    "/{trip_id}",
    response_model=TripDetail,
    summary="Retrieve a trip (expanded) by UUID or confirmation code",
    responses=error_responses(404, 422),
)
def get_trip(
    trips: TripsDep,
    bookings: BookingsDep,
    trip_id: Annotated[
        str,
        Path(
            description="Trip UUID *or* TRP-XXXXXX confirmation code",
            examples=["TRP-AB23XY"],
        ),
    ],
) -> TripDetail:
    """Return a trip with its bookings and itinerary places resolved in full.

    Accepts the UUID or the ``TRP-XXXXXX`` code interchangeably; 404 if
    neither matches.
    """
    return trips.get_detail(trip_id, booking_service=bookings)


@router.patch(
    "/{trip_id}",
    response_model=Trip,
    summary="Amend a trip (partial update)",
    responses=error_responses(404, 422),
)
def update_trip(
    request: TripUpdateRequest,
    trips: TripsDep,
    bookings: BookingsDep,
    trip_id: Annotated[
        str,
        Path(
            description="Trip UUID *or* TRP-XXXXXX confirmation code",
            examples=["TRP-AB23XY"],
        ),
    ],
) -> Trip:
    """Apply a partial update — only the fields you send are changed.

    Changing the city/dates/references re-runs the same validation as create
    (404 for an unknown city/booking/place, 422 for a bad date range).
    """
    try:
        return trips.update(trip_id, request, booking_service=bookings)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.delete(
    "/{trip_id}",
    response_model=Trip,
    summary="Cancel a trip by UUID or confirmation code",
    responses=error_responses(404, 422),
)
def cancel_trip(
    trips: TripsDep,
    trip_id: Annotated[
        str,
        Path(
            description="Trip UUID *or* TRP-XXXXXX confirmation code",
            examples=["TRP-AB23XY"],
        ),
    ],
) -> Trip:
    """Soft-cancel a trip — ``status`` becomes ``cancelled``, the row is kept.

    Idempotent: cancelling an already-cancelled trip is a no-op. 404 if no
    trip matches.
    """
    return trips.cancel(trip_id)
