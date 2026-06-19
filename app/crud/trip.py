"""Data-access layer for trips — SQLAlchemy ORM persistence, nothing else.

The ``crud`` tier reads/writes trip, trip_item, and trip_place_link rows;
business rules (ID generation, existence checks, 404s) live in
``services/trip_service.py``. A fresh session per call (threadpool-safe for
sync endpoints), idempotent ``init_db``. JSON columns (``budget_caps``) are
native (no manual json.dumps/loads). Link methods return plain dicts so the
service can read them by key (``row["col"]``) exactly as before.
"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.base import Base
from app.db.models import TripItemRow, TripPlaceLinkRow, TripRow
from app.schemas.trip import Trip, TripItem


def _iso(value) -> str | None:
    """Serialise a date/datetime to ISO text, passing through None and str."""
    return value.isoformat() if hasattr(value, "isoformat") else value


def _row_to_item(row: TripItemRow) -> TripItem:
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


def _row_to_trip(row: TripRow, item_rows: list[TripItemRow]) -> Trip:
    items = sorted(
        (_row_to_item(r) for r in item_rows), key=lambda i: (i.day, i.sort_order)
    )
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


def _link_to_dict(row: TripPlaceLinkRow) -> dict:
    return {
        "id": row.id,
        "trip_id": row.trip_id,
        "place_id": row.place_id,
        "source": row.source,
        "added_at": row.added_at,
    }


def _new_trip_row(trip: Trip, idempotency_key: str | None) -> TripRow:
    return TripRow(
        id=trip.id,
        title=trip.title,
        city=trip.city,
        start_date=_iso(trip.start_date),
        end_date=_iso(trip.end_date),
        travelers=trip.travelers,
        notes=trip.notes,
        created_at=_iso(trip.created_at),
        idempotency_key=idempotency_key,
    )


def _new_item_row(item: TripItem, idempotency_key: str | None) -> TripItemRow:
    return TripItemRow(
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


class TripRepository:
    """ORM-backed store of trip + trip_item + trip_place_link rows."""

    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    def init_db(self) -> None:
        Base.metadata.create_all(self._sf().get_bind(), checkfirst=True)

    def create_trip(self, trip: Trip, idempotency_key: str | None = None) -> Trip:
        """Insert a trip and all of its items in one transaction.

        ``idempotency_key`` is stored on the trip row so a repeat request can
        be detected via :meth:`get_trip_by_idempotency_key`. If a concurrent
        request already inserted a trip under the same key, the UNIQUE index
        makes this INSERT fail; we return the winner's trip instead of raising.
        """
        try:
            with self._sf() as s:
                s.add(_new_trip_row(trip, idempotency_key))
                s.add_all([_new_item_row(item, None) for item in trip.items])
                s.commit()
        except IntegrityError:
            if idempotency_key is not None:
                existing = self.get_trip_by_idempotency_key(idempotency_key)
                if existing is not None:
                    return existing
            raise
        return trip

    def get_trip(self, trip_id: str) -> Trip | None:
        with self._sf() as s:
            row = s.scalars(
                select(TripRow).where(
                    TripRow.id == trip_id, TripRow.deleted_at.is_(None)
                )
            ).first()
            if row is None:
                return None
            item_rows = s.scalars(
                select(TripItemRow).where(TripItemRow.trip_id == trip_id)
            ).all()
            return _row_to_trip(row, item_rows)

    def list_trips(self) -> list[Trip]:
        """Return every trip (newest first) with its items attached."""
        with self._sf() as s:
            trip_rows = s.scalars(
                select(TripRow)
                .where(TripRow.deleted_at.is_(None))
                .order_by(TripRow.created_at.desc())
            ).all()
            item_rows = s.scalars(select(TripItemRow)).all()
            by_trip: dict[str, list[TripItemRow]] = {}
            for r in item_rows:
                by_trip.setdefault(r.trip_id, []).append(r)
            return [_row_to_trip(t, by_trip.get(t.id, [])) for t in trip_rows]

    def update_trip(self, trip: Trip) -> bool:
        """Replace a trip's top-level columns. Returns True if a row changed."""
        with self._sf() as s:
            row = s.get(TripRow, trip.id)
            if row is None:
                return False
            row.title = trip.title
            row.city = trip.city
            row.start_date = _iso(trip.start_date)
            row.end_date = _iso(trip.end_date)
            row.travelers = trip.travelers
            row.notes = trip.notes
            s.commit()
            return True

    def delete_trip(self, trip_id: str, *, when: str) -> bool:
        """Soft-delete: stamp deleted_at, keep the row. True if it existed and
        was live.

        The idempotency_key is cleared on tombstoning: it is only meaningful for
        replaying *live* trips, and the UNIQUE key index spans all rows —
        leaving it would make a later create that reuses the key collide with
        the dead row (which the deleted_at-filtered replay lookup can't
        recover).
        """
        with self._sf() as s:
            row = s.scalars(
                select(TripRow).where(
                    TripRow.id == trip_id, TripRow.deleted_at.is_(None)
                )
            ).first()
            if row is None:
                return False
            row.deleted_at = when
            row.idempotency_key = None
            s.commit()
            return True

    def get_budget_caps(self, trip_id: str) -> dict[str, float]:
        """Return the trip's per-category caps as a dict (empty if unset).

        No existence check here — the service has already 404'd a missing trip.
        A tombstoned/unknown trip simply yields {}.
        """
        with self._sf() as s:
            row = s.scalars(
                select(TripRow).where(
                    TripRow.id == trip_id, TripRow.deleted_at.is_(None)
                )
            ).first()
            if row is None or row.budget_caps is None:
                return {}
            return dict(row.budget_caps)

    def set_budget_caps(self, trip_id: str, caps: dict[str, float]) -> None:
        """Persist the trip's caps (replace). {} clears all caps.

        Expects the service-filtered, float-only caps dict (None/uncapped
        categories are dropped by the service before calling). No existence
        check here — the service has already 404'd a missing trip; a
        tombstoned/unknown trip is a silent no-op.
        """
        with self._sf() as s:
            row = s.scalars(
                select(TripRow).where(
                    TripRow.id == trip_id, TripRow.deleted_at.is_(None)
                )
            ).first()
            if row is None:
                return
            row.budget_caps = caps
            s.commit()

    def add_item(self, item: TripItem, idempotency_key: str | None = None) -> TripItem:
        """Insert an item and return it.

        ``idempotency_key`` is stored on the row so a repeat request can be
        detected via :meth:`get_item_by_idempotency_key`. If a concurrent
        request already inserted an item under the same key, the UNIQUE index
        makes this INSERT fail; we return the winner's item instead of raising.
        """
        try:
            with self._sf() as s:
                s.add(_new_item_row(item, idempotency_key))
                s.commit()
        except IntegrityError:
            if idempotency_key is not None:
                existing = self.get_item_by_idempotency_key(idempotency_key)
                if existing is not None:
                    return existing
            raise
        return item

    def get_trip_by_idempotency_key(self, key: str) -> Trip | None:
        with self._sf() as s:
            row = s.scalars(
                select(TripRow).where(
                    TripRow.idempotency_key == key, TripRow.deleted_at.is_(None)
                )
            ).first()
            if row is None:
                return None
            items = s.scalars(
                select(TripItemRow).where(TripItemRow.trip_id == row.id)
            ).all()
            return _row_to_trip(row, items)

    def get_item_by_idempotency_key(self, key: str) -> TripItem | None:
        with self._sf() as s:
            row = s.scalars(
                select(TripItemRow).where(TripItemRow.idempotency_key == key)
            ).first()
            return _row_to_item(row) if row is not None else None

    def get_item(self, item_id: str) -> TripItem | None:
        with self._sf() as s:
            row = s.get(TripItemRow, item_id)
            return _row_to_item(row) if row is not None else None

    def update_item(self, item: TripItem) -> bool:
        with self._sf() as s:
            row = s.get(TripItemRow, item.id)
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
            s.commit()
            return True

    def delete_item(self, item_id: str) -> bool:
        with self._sf() as s:
            row = s.get(TripItemRow, item_id)
            if row is None:
                return False
            s.delete(row)
            s.commit()
            return True

    # --- trip_place_link (shortlist) ------------------------------------- #

    def add_trip_place(
        self, link_id: str, trip_id: str, place_id: str, source: str, added_at: str
    ) -> None:
        """Insert a shortlist link. Re-raises sqlalchemy IntegrityError on the
        (trip_id, place_id, source) UNIQUE collision — the service maps it
        to a 409."""
        with self._sf() as s:
            s.add(
                TripPlaceLinkRow(
                    id=link_id,
                    trip_id=trip_id,
                    place_id=place_id,
                    source=source,
                    added_at=added_at,
                )
            )
            s.commit()

    def list_trip_places(self, trip_id: str) -> list[dict]:
        with self._sf() as s:
            rows = s.scalars(
                select(TripPlaceLinkRow)
                .where(TripPlaceLinkRow.trip_id == trip_id)
                .order_by(TripPlaceLinkRow.added_at)
            ).all()
            return [_link_to_dict(r) for r in rows]

    def get_trip_place(self, link_id: str) -> dict | None:
        with self._sf() as s:
            row = s.get(TripPlaceLinkRow, link_id)
            return _link_to_dict(row) if row is not None else None

    def delete_trip_place(self, trip_id: str, link_id: str) -> bool:
        """Delete a shortlist link scoped to its trip. True if a row was
        removed."""
        with self._sf() as s:
            row = s.scalars(
                select(TripPlaceLinkRow).where(
                    TripPlaceLinkRow.id == link_id,
                    TripPlaceLinkRow.trip_id == trip_id,
                )
            ).first()
            if row is None:
                return False
            s.delete(row)
            s.commit()
            return True
