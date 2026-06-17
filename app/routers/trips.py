"""Trip itinerary endpoints: CRUD over trips and their day-plan items."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.schemas.error import error_responses
from app.schemas.pagination import PaginationDep
from app.schemas.trip import (
    Trip,
    TripCreate,
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
def create_trip(trips: TripsDep, body: TripCreate) -> Trip:
    """Create a trip and return it, including any items sorted by day."""
    return trips.create_trip(body)


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
    response_model=Trip,
    summary="Retrieve one trip by UUID",
    responses=error_responses(404, 422),
)
def get_trip(trips: TripsDep, trip_id: _TRIP_ID) -> Trip:
    """Return a trip and its items. 404 if the UUID is unknown."""
    return trips.get_trip(trip_id)


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
    responses=error_responses(404, 422),
)
def add_item(trips: TripsDep, trip_id: _TRIP_ID, body: TripItemCreate) -> TripItem:
    """Append a day-plan item to the trip. 404 if the trip is unknown."""
    return trips.add_item(trip_id, body)


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
