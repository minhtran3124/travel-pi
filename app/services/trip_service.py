"""Trip itinerary business logic: CRUD over trips and their items.

Service tier — owns ID generation, existence checks, and the 404s; delegates
all persistence to :class:`~app.crud.trip.TripRepository`. Trips are the
second mutable state in the API (alongside bookings). Sync + raw SQLite, like
the booking service.
"""

import logging
import uuid
from datetime import datetime, timezone

from app.core.config import get_settings
from app.crud.trip import TripRepository
from app.exceptions import NotFoundError
from app.schemas.trip import (
    Trip,
    TripCreate,
    TripItem,
    TripItemCreate,
    TripItemUpdate,
    TripUpdate,
)

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return str(uuid.uuid4())


class TripService:
    """Business logic over the trip store."""

    def __init__(self, db_path: str) -> None:
        self._repo = TripRepository(db_path)

    def init_db(self) -> None:
        """Create the backing tables. Called once on application startup."""
        self._repo.init_db()

    def get_trip(self, trip_id: str) -> Trip:
        """Return a trip by UUID, or raise :class:`NotFoundError`."""
        trip = self._repo.get_trip(trip_id)
        if trip is None:
            raise NotFoundError(
                f"Trip {trip_id!r} not found",
                hint="Use GET /trips to list existing trips.",
            )
        return trip

    def list_trips(self) -> list[Trip]:
        """Return every trip, newest first."""
        return self._repo.list_trips()

    def create_trip(self, request: TripCreate) -> Trip:
        """Create a trip (plus any initial items) and return it."""
        trip_id = _new_id()
        items = [
            TripItem(id=_new_id(), trip_id=trip_id, **item.model_dump())
            for item in request.items
        ]
        trip = Trip(
            id=trip_id,
            title=request.title,
            city=request.city,
            start_date=request.start_date,
            end_date=request.end_date,
            travelers=request.travelers,
            notes=request.notes,
            created_at=datetime.now(timezone.utc),
            items=items,
        )
        self._repo.create_trip(trip)
        logger.info("Created trip %s with %d item(s)", trip_id, len(items))
        return self._repo.get_trip(trip_id)

    def update_trip(self, trip_id: str, request: TripUpdate) -> Trip:
        """Replace a trip's top-level fields. 404 if it does not exist."""
        existing = self.get_trip(trip_id)
        updated = existing.model_copy(
            update={
                "title": request.title,
                "city": request.city,
                "start_date": request.start_date,
                "end_date": request.end_date,
                "travelers": request.travelers,
                "notes": request.notes,
            }
        )
        self._repo.update_trip(updated)
        logger.info("Updated trip %s", trip_id)
        return self._repo.get_trip(trip_id)

    def delete_trip(self, trip_id: str) -> None:
        """Delete a trip and its items. 404 if it does not exist."""
        self.get_trip(trip_id)
        self._repo.delete_trip(trip_id)
        logger.info("Deleted trip %s", trip_id)

    def add_item(self, trip_id: str, request: TripItemCreate) -> TripItem:
        """Append an item to a trip. 404 if the trip does not exist."""
        self.get_trip(trip_id)
        item = TripItem(id=_new_id(), trip_id=trip_id, **request.model_dump())
        self._repo.add_item(item)
        logger.info("Added item %s to trip %s", item.id, trip_id)
        return item

    def update_item(
        self, trip_id: str, item_id: str, request: TripItemUpdate
    ) -> TripItem:
        """Replace an item's fields. 404 if the trip or item does not match."""
        self.get_trip(trip_id)
        existing = self._repo.get_item(item_id)
        if existing is None or existing.trip_id != trip_id:
            raise NotFoundError(
                f"Item {item_id!r} not found on trip {trip_id!r}",
                hint="Use GET /trips/{trip_id} to see its items.",
            )
        updated = TripItem(id=item_id, trip_id=trip_id, **request.model_dump())
        self._repo.update_item(updated)
        return self._repo.get_item(item_id)

    def delete_item(self, trip_id: str, item_id: str) -> None:
        """Delete an item from a trip. 404 if the trip or item does not match."""
        self.get_trip(trip_id)
        existing = self._repo.get_item(item_id)
        if existing is None or existing.trip_id != trip_id:
            raise NotFoundError(
                f"Item {item_id!r} not found on trip {trip_id!r}",
                hint="Use GET /trips/{trip_id} to see its items.",
            )
        self._repo.delete_item(item_id)
        logger.info("Deleted item %s from trip %s", item_id, trip_id)


# Shared singleton — constructed at import time (cheap: stores the path only).
# The tables are created later from the app's lifespan handler, so importing
# this module has no side effects.
_trip_service = TripService(get_settings().database_path)


def get_trip_service() -> TripService:
    """FastAPI dependency returning the shared trip store."""
    return _trip_service
