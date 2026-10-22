"""Data-access layer for trips; business rules live in services/trip_service.py."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db import models
from app.db.base import Base
from app.repositories.base import Repo
from app.schemas.trip import Trip, TripItem


def _iso(value) -> str | None:
    """Serialise a date/datetime to ISO text; pass through str/None unchanged."""
    return value.isoformat() if hasattr(value, "isoformat") else value


def _row_to_item(row: models.TripItem) -> TripItem:
    return TripItem(
        id=row.id,
        trip_id=row.trip_id,
        day=row.day,
        sort_order=row.sort_order,
        kind=row.kind,
        title=row.title,
        place_id=row.place_id,
        booking_id=row.booking_id,
        start_time=row.start_time,
        notes=row.notes,
        status=row.status,
    )


def _row_to_trip(row: models.Trip, item_rows: list[models.TripItem]) -> Trip:
    # Sort so (day, sort_order) ties break on (created_at, id), not nondeterministic DB return order.
    sorted_rows = sorted(
        item_rows, key=lambda r: (r.day, r.sort_order, r.created_at, r.id)
    )
    items = [_row_to_item(r) for r in sorted_rows]
    return Trip(
        id=row.id,
        title=row.title,
        city=row.city,
        start_date=row.start_date,
        end_date=row.end_date,
        travelers=row.travelers,
        notes=row.notes,
        created_at=row.created_at,
        items=items,
    )


def _link_to_dict(row: models.TripPlaceLink) -> dict:
    return {
        "id": row.id,
        "trip_id": row.trip_id,
        "place_id": row.place_id,
        "source": row.source,
        "added_at": row.added_at,
    }


def _new_trip_row(trip: Trip, idempotency_key: str | None, user_id: str) -> models.Trip:
    return models.Trip(
        id=trip.id,
        user_id=user_id,
        title=trip.title,
        city=trip.city,
        start_date=_iso(trip.start_date),
        end_date=_iso(trip.end_date),
        travelers=trip.travelers,
        notes=trip.notes,
        created_at=_iso(trip.created_at),
        idempotency_key=idempotency_key,
    )


def _new_item_row(item: TripItem, idempotency_key: str | None) -> models.TripItem:
    return models.TripItem(
        id=item.id,
        trip_id=item.trip_id,
        day=item.day,
        sort_order=item.sort_order,
        kind=item.kind.value,
        title=item.title,
        place_id=item.place_id,
        booking_id=item.booking_id,
        start_time=item.start_time,
        notes=item.notes,
        idempotency_key=idempotency_key,
        status=item.status.value,
    )


class TripRepository(Repo):
    """ORM-backed store of trip + trip_item + trip_place_link rows."""

    def init_db(self) -> None:
        Base.metadata.create_all(self._bind(), checkfirst=True)

    def create_trip(
        self, trip: Trip, user_id: str, idempotency_key: str | None = None
    ) -> Trip:
        """Insert a trip and its items in one transaction; on an idempotency_key race, return the winner instead of raising."""
        try:
            with self._session() as s:
                with s.begin_nested():  # savepoint: keep a shared (UoW) session usable
                    s.add(_new_trip_row(trip, idempotency_key, user_id))
                    s.add_all([_new_item_row(item, None) for item in trip.items])
                self._commit(s)
        except IntegrityError:
            if idempotency_key is not None:
                existing = self.get_trip_by_idempotency_key(idempotency_key, user_id)
                if existing is not None:
                    return existing
            raise
        return trip

    def get_trip(self, trip_id: str, user_id: str) -> Trip | None:
        """Return the caller's trip, or None; a foreign owner's trip is indistinguishable from missing (no existence leak)."""
        with self._session() as s:
            row = s.scalars(
                select(models.Trip).where(
                    models.Trip.id == trip_id,
                    models.Trip.user_id == user_id,
                    models.Trip.deleted_at.is_(None),
                )
            ).first()
            if row is None:
                return None
            item_rows = s.scalars(
                select(models.TripItem).where(models.TripItem.trip_id == trip_id)
            ).all()
            return _row_to_trip(row, item_rows)

    def list_trips(self, user_id: str) -> list[Trip]:
        """Return the caller's live trips, newest first, each with its items attached."""
        with self._session() as s:
            trip_rows = s.scalars(
                select(models.Trip)
                .where(
                    models.Trip.user_id == user_id,
                    models.Trip.deleted_at.is_(None),
                )
                .order_by(models.Trip.created_at.desc())
            ).all()
            item_rows = s.scalars(select(models.TripItem)).all()
            by_trip: dict[str, list[models.TripItem]] = {}
            for r in item_rows:
                by_trip.setdefault(r.trip_id, []).append(r)
            return [_row_to_trip(t, by_trip.get(t.id, [])) for t in trip_rows]

    def update_trip(self, trip: Trip) -> bool:
        with self._session() as s:
            row = s.get(models.Trip, trip.id)
            if row is None:
                return False
            row.title = trip.title
            row.city = trip.city
            row.start_date = _iso(trip.start_date)
            row.end_date = _iso(trip.end_date)
            row.travelers = trip.travelers
            row.notes = trip.notes
            self._commit(s)
            return True

    def delete_trip(self, trip_id: str, *, when: str) -> bool:
        """Soft-delete: stamp deleted_at and clear idempotency_key so a later create reusing the key won't collide with the dead row."""
        with self._session() as s:
            row = s.scalars(
                select(models.Trip).where(
                    models.Trip.id == trip_id, models.Trip.deleted_at.is_(None)
                )
            ).first()
            if row is None:
                return False
            row.deleted_at = when
            row.idempotency_key = None
            self._commit(s)
            return True

    def get_budget_caps(self, trip_id: str) -> dict[str, float]:
        """Return the trip's per-category caps, or {}; no existence check (the service already 404'd a missing trip)."""
        with self._session() as s:
            row = s.scalars(
                select(models.Trip).where(
                    models.Trip.id == trip_id, models.Trip.deleted_at.is_(None)
                )
            ).first()
            if row is None or row.budget_caps is None:
                return {}
            return dict(row.budget_caps)

    def set_budget_caps(self, trip_id: str, caps: dict[str, float]) -> None:
        """Persist the trip's caps (replace); {} clears all. No existence check — a missing/tombstoned trip is a silent no-op."""
        with self._session() as s:
            row = s.scalars(
                select(models.Trip).where(
                    models.Trip.id == trip_id, models.Trip.deleted_at.is_(None)
                )
            ).first()
            if row is None:
                return
            row.budget_caps = caps
            self._commit(s)

    def add_item(self, item: TripItem, idempotency_key: str | None = None) -> TripItem:
        """Insert an item; on an idempotency_key race, return the winner instead of raising."""
        try:
            with self._session() as s:
                with s.begin_nested():  # savepoint: keep a shared (UoW) session usable
                    s.add(_new_item_row(item, idempotency_key))
                self._commit(s)
        except IntegrityError:
            if idempotency_key is not None:
                existing = self.get_item_by_idempotency_key(idempotency_key)
                if existing is not None:
                    return existing
            raise
        return item

    def get_trip_by_idempotency_key(self, key: str, user_id: str) -> Trip | None:
        """Replay lookup scoped to the caller — the idempotency index is global, so an unscoped match could leak another user's trip."""
        with self._session() as s:
            row = s.scalars(
                select(models.Trip).where(
                    models.Trip.idempotency_key == key,
                    models.Trip.user_id == user_id,
                    models.Trip.deleted_at.is_(None),
                )
            ).first()
            if row is None:
                return None
            items = s.scalars(
                select(models.TripItem).where(models.TripItem.trip_id == row.id)
            ).all()
            return _row_to_trip(row, items)

    def get_item_by_idempotency_key(self, key: str) -> TripItem | None:
        with self._session() as s:
            row = s.scalars(
                select(models.TripItem).where(models.TripItem.idempotency_key == key)
            ).first()
            return _row_to_item(row) if row is not None else None

    def get_item(self, item_id: str) -> TripItem | None:
        with self._session() as s:
            row = s.get(models.TripItem, item_id)
            return _row_to_item(row) if row is not None else None

    def update_item(self, item: TripItem) -> bool:
        with self._session() as s:
            row = s.get(models.TripItem, item.id)
            if row is None:
                return False
            row.day = item.day
            row.sort_order = item.sort_order
            row.kind = item.kind.value
            row.title = item.title
            row.place_id = item.place_id
            row.booking_id = item.booking_id
            row.start_time = item.start_time
            row.notes = item.notes
            row.status = item.status.value
            self._commit(s)
            return True

    def delete_item(self, item_id: str) -> bool:
        with self._session() as s:
            row = s.get(models.TripItem, item_id)
            if row is None:
                return False
            s.delete(row)
            self._commit(s)
            return True

    # --- trip_place_link (shortlist) ------------------------------------- #

    def add_trip_place(
        self, link_id: str, trip_id: str, place_id: str, source: str, added_at: str
    ) -> None:
        """Insert a shortlist link; re-raises IntegrityError on the (trip_id, place_id, source) UNIQUE collision (service maps to 409)."""
        with self._session() as s:
            s.add(
                models.TripPlaceLink(
                    id=link_id,
                    trip_id=trip_id,
                    place_id=place_id,
                    source=source,
                    added_at=added_at,
                )
            )
            self._commit(s)

    def list_trip_places(self, trip_id: str) -> list[dict]:
        with self._session() as s:
            rows = s.scalars(
                select(models.TripPlaceLink)
                .where(models.TripPlaceLink.trip_id == trip_id)
                .order_by(models.TripPlaceLink.added_at)
            ).all()
            return [_link_to_dict(r) for r in rows]

    def get_trip_place(self, link_id: str) -> dict | None:
        with self._session() as s:
            row = s.get(models.TripPlaceLink, link_id)
            return _link_to_dict(row) if row is not None else None

    def delete_trip_place(self, trip_id: str, link_id: str) -> bool:
        with self._session() as s:
            row = s.scalars(
                select(models.TripPlaceLink).where(
                    models.TripPlaceLink.id == link_id,
                    models.TripPlaceLink.trip_id == trip_id,
                )
            ).first()
            if row is None:
                return False
            s.delete(row)
            self._commit(s)
            return True
