"""Trip itinerary endpoints: CRUD over trips and their day-plan items."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, status

from app.schemas.error import error_responses
from app.schemas.pagination import PaginationDep
from app.schemas.saved_place import ShortlistEntry
from app.schemas.trip import (
    AddTripPlaceRequest,
    DayPlanResponse,
    Trip,
    TripBudget,
    TripBudgetSet,
    TripCreate,
    TripDetail,
    TripEstimateRequest,
    TripEstimateResponse,
    TripItem,
    TripItemCreate,
    TripItemUpdate,
    TripListResponse,
    TripUpdate,
)
from app.services.trip_service import TripService, estimate_trip, get_trip_service

router = APIRouter(prefix="/trips", tags=["trips"])

TripsDep = Annotated[TripService, Depends(get_trip_service)]

_TRIP_ID = Annotated[str, Path(description="Trip UUID", examples=["c1e1f5a4-..."])]
_ITEM_ID = Annotated[str, Path(description="Item UUID", examples=["a2b4c6d8-..."])]


@router.post(
    "",
    response_model=Trip,
    status_code=status.HTTP_201_CREATED,
    summary="Create a trip itinerary (with optional initial items)",
    responses=error_responses(422),
)
def create_trip(
    trips: TripsDep,
    body: TripCreate,
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            description=(
                "Optional client-supplied key that makes this POST "
                "replay-safe: repeating the request with the same key "
                "returns the original trip instead of creating a "
                "duplicate."
            ),
            examples=["trip-2026-06-01-abc123"],
        ),
    ] = None,
) -> Trip:
    """Create a trip and return it, including any items sorted by day."""
    return trips.create_trip(body, idempotency_key=idempotency_key)


@router.post(
    "/estimate",
    response_model=TripEstimateResponse,
    summary="Estimate a trip's budget (calculation only — nothing is stored)",
    responses=error_responses(422),
)
def estimate_trip_budget(body: TripEstimateRequest) -> TripEstimateResponse:
    """Compute a line-item budget estimate. Pure calculation; no DB, no state."""
    return estimate_trip(body)


@router.get(
    "",
    response_model=TripListResponse,
    summary="List trips (paginated, newest first)",
    responses=error_responses(422),
)
def list_trips(trips: TripsDep, pagination: PaginationDep) -> TripListResponse:
    """Return trips with the shared limit/offset pagination envelope."""
    page, total = pagination.page_of(trips.list_trips())
    return TripListResponse(
        total=total, limit=pagination.limit, offset=pagination.offset, results=page
    )


@router.get(
    "/{trip_id}",
    response_model=TripDetail,
    summary="Retrieve one trip by UUID (includes computed total_spent and gaps)",
    responses=error_responses(404, 422),
)
def get_trip(trips: TripsDep, trip_id: _TRIP_ID) -> TripDetail:
    """Return a trip and its items enriched with total_spent and coverage gaps.

    ``total_spent`` sums linked non-cancelled booking prices (USD).
    ``gaps`` lists days missing accommodation or with no planned items.
    404 if the UUID is unknown.
    """
    return trips.get_trip_detail(trip_id)


@router.get(
    "/{trip_id}/day-plan",
    response_model=DayPlanResponse,
    summary="Day-by-day plan for a date, with travel time between stops",
    responses=error_responses(404, 409),
)
async def get_day_plan(
    trips: TripsDep,
    trip_id: _TRIP_ID,
    date: Annotated[
        date, Query(description="Calendar date within the trip (YYYY-MM-DD).")
    ],
) -> DayPlanResponse:
    """Return the ordered day plan for a single date, with travel-time annotations.

    409 if the trip has no start_date set (day number cannot be derived).
    404 if the trip UUID is unknown.
    """
    return await trips.get_day_plan(trip_id, date)


@router.get(
    "/{trip_id}/budget",
    response_model=TripBudget,
    summary="Per-category budget: caps (planned) vs booked spend",
    responses=error_responses(404, 422),
)
def get_trip_budget(trips: TripsDep, trip_id: _TRIP_ID) -> TripBudget:
    """Return flights/hotels/activities/buffer caps vs spent vs remaining.

    'spent' rolls up linked, non-cancelled bookings by type (activities/buffer
    have no booking source yet, so 0). 404 if the trip UUID is unknown.
    """
    return trips.get_trip_budget(trip_id)


@router.post(
    "/{trip_id}/budget",
    response_model=TripBudget,
    summary="Set a trip's per-category budget caps (replace)",
    responses=error_responses(404, 422),
)
def set_trip_budget(
    trips: TripsDep, trip_id: _TRIP_ID, body: TripBudgetSet
) -> TripBudget:
    """Replace the trip's caps and return the budget. Every POST fully replaces
    the caps — omitted categories become uncapped. 404 if the trip is unknown.

    Once set, POST /trips/{id}/items returns 409 when a linked booking would
    push that category's spend over its cap.
    """
    return trips.set_trip_budget(trip_id, body)


@router.put(
    "/{trip_id}",
    response_model=Trip,
    summary="Replace a trip's top-level fields",
    responses=error_responses(404, 422),
)
def update_trip(trips: TripsDep, trip_id: _TRIP_ID, body: TripUpdate) -> Trip:
    """Replace the trip's title/city/dates/travelers/notes. Items unchanged."""
    return trips.update_trip(trip_id, body)


@router.delete(
    "/{trip_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a trip and its items",
    responses=error_responses(404, 422),
)
def delete_trip(trips: TripsDep, trip_id: _TRIP_ID) -> None:
    """Hard-delete a trip and all of its items. 404 if unknown."""
    trips.delete_trip(trip_id)


@router.post(
    "/{trip_id}/items",
    response_model=TripItem,
    status_code=status.HTTP_201_CREATED,
    summary="Add an item to a trip",
    responses=error_responses(404, 409, 422),  # 409 = over budget
)
def add_item(
    trips: TripsDep,
    trip_id: _TRIP_ID,
    body: TripItemCreate,
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            description=(
                "Optional client-supplied key that makes this POST "
                "replay-safe: repeating the request with the same key "
                "returns the original item instead of creating a "
                "duplicate."
            ),
            examples=["item-2026-06-01-abc123"],
        ),
    ] = None,
) -> TripItem:
    """Append a day-plan item to the trip. 404 if the trip is unknown.

    409 if a linked booking would exceed a budget cap.
    """
    return trips.add_item(trip_id, body, idempotency_key=idempotency_key)


@router.put(
    "/{trip_id}/items/{item_id}",
    response_model=TripItem,
    summary="Replace an item on a trip",
    responses=error_responses(404, 422),
)
def update_item(
    trips: TripsDep, trip_id: _TRIP_ID, item_id: _ITEM_ID, body: TripItemUpdate
) -> TripItem:
    """Replace an item's fields. 404 if the trip or item does not match."""
    return trips.update_item(trip_id, item_id, body)


@router.delete(
    "/{trip_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an item from a trip",
    responses=error_responses(404, 422),
)
def delete_item(trips: TripsDep, trip_id: _TRIP_ID, item_id: _ITEM_ID) -> None:
    """Delete one item. 404 if the trip or item does not match."""
    trips.delete_item(trip_id, item_id)


_LINK_ID = Annotated[
    str,
    Path(description="Shortlist link id (trip_place_link.id)", examples=["a2b4..."]),
]


@router.post(
    "/{trip_id}/places",
    response_model=ShortlistEntry,
    status_code=status.HTTP_201_CREATED,
    summary="Shortlist a place (catalog or saved) onto a trip",
    responses=error_responses(404, 409, 422),
)
def add_trip_place(
    trips: TripsDep, trip_id: _TRIP_ID, body: AddTripPlaceRequest
) -> ShortlistEntry:
    """Add a place to the trip's shortlist. 404 if the trip or place is unknown,
    409 if it is already shortlisted."""
    return trips.add_place_to_trip(trip_id, body.place_id, body.source)


@router.get(
    "/{trip_id}/places",
    response_model=list[ShortlistEntry],
    summary="List a trip's shortlisted places",
    responses=error_responses(404),
)
def list_trip_places(trips: TripsDep, trip_id: _TRIP_ID) -> list[ShortlistEntry]:
    """Return the trip's shortlist, each entry resolved to its place body."""
    return trips.list_trip_places(trip_id)


@router.delete(
    "/{trip_id}/places/{link_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a place from a trip's shortlist",
    responses=error_responses(404),
)
def remove_trip_place(trips: TripsDep, trip_id: _TRIP_ID, link_id: _LINK_ID) -> None:
    """Remove a shortlist entry. 404 if the trip or link does not match."""
    trips.remove_trip_place(trip_id, link_id)
