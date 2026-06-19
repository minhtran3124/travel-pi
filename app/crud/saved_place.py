"""Data-access layer for saved places — SQLAlchemy ORM persistence only.

The ``crud`` tier reads/writes ``saved_places`` rows; business rules (ID
generation, existence checks, 404/409s, dedup policy) live in
``services/saved_place_service.py``. A fresh session per call (threadpool-safe
for sync endpoints), idempotent ``init_db``, soft-delete filtered from reads.
The ``links`` column is a native JSON column (no manual json.dumps/loads).
"""

from sqlalchemy import func, select

from app.core.geo import haversine_km
from app.db.base import Base
from app.db.models import SavedPlaceRow
from app.schemas.saved_place import SavedPlace

_SET_FLAG_FIELDS = {"favorite", "visited"}


def _row_to_saved_place(row: SavedPlaceRow) -> SavedPlace:
    return SavedPlace(
        id=row.id,
        name=row.name,
        city=row.city,
        country=row.country,
        category=row.category,
        address=row.address,
        latitude=row.latitude,
        longitude=row.longitude,
        price_level=row.price_level,
        notes=row.notes,
        favorite=bool(row.favorite),
        visited=bool(row.visited),
        links=row.links,
        duration=row.duration,
        created_at=row.created_at,
    )


class SavedPlaceRepository:
    """ORM-backed store of saved_places rows."""

    def __init__(self, session_factory) -> None:
        self._sf = session_factory

    def init_db(self) -> None:
        Base.metadata.create_all(self._sf().get_bind(), checkfirst=True)

    def add(self, sp: SavedPlace) -> SavedPlace:
        row = SavedPlaceRow(
            id=sp.id,
            name=sp.name,
            city=sp.city,
            country=sp.country,
            category=sp.category,
            address=sp.address,
            latitude=sp.latitude,
            longitude=sp.longitude,
            price_level=sp.price_level,
            notes=sp.notes,
            favorite=bool(sp.favorite),
            visited=bool(sp.visited),
            links=sp.links,
            duration=sp.duration,
            created_at=sp.created_at,
        )
        with self._sf() as s:
            s.add(row)
            s.commit()
        return sp

    def get(self, id_: str) -> SavedPlace | None:
        """Fetch a live saved place by raw UUID or SPL- short code.

        The short code is derived (not stored), so a code lookup scans the
        live rows and matches on the computed ``short_code`` in Python.
        """
        with self._sf() as s:
            row = s.scalars(
                select(SavedPlaceRow).where(
                    SavedPlaceRow.id == id_, SavedPlaceRow.deleted_at.is_(None)
                )
            ).first()
            if row is not None:
                return _row_to_saved_place(row)
            rows = s.scalars(
                select(SavedPlaceRow).where(SavedPlaceRow.deleted_at.is_(None))
            ).all()
            wanted = id_.upper()
            for r in rows:
                sp = _row_to_saved_place(r)
                if sp.short_code.upper() == wanted:
                    return sp
        return None

    def list(
        self,
        *,
        city: str | None = None,
        category: str | None = None,
        favorite: bool | None = None,
        visited: bool | None = None,
    ) -> list[SavedPlace]:
        stmt = select(SavedPlaceRow).where(SavedPlaceRow.deleted_at.is_(None))
        if city is not None:
            stmt = stmt.where(func.lower(SavedPlaceRow.city) == func.lower(city))
        if category is not None:
            stmt = stmt.where(
                func.lower(SavedPlaceRow.category) == func.lower(category)
            )
        if favorite is not None:
            stmt = stmt.where(SavedPlaceRow.favorite == bool(favorite))
        if visited is not None:
            stmt = stmt.where(SavedPlaceRow.visited == bool(visited))
        stmt = stmt.order_by(SavedPlaceRow.created_at.desc(), SavedPlaceRow.id.desc())
        with self._sf() as s:
            return [_row_to_saved_place(r) for r in s.scalars(stmt).all()]

    def soft_delete(self, id_: str, *, when: str) -> bool:
        """Stamp deleted_at; True if a live row existed and was tombstoned."""
        with self._sf() as s:
            row = s.scalars(
                select(SavedPlaceRow).where(
                    SavedPlaceRow.id == id_, SavedPlaceRow.deleted_at.is_(None)
                )
            ).first()
            if row is None:
                return False
            row.deleted_at = when
            s.commit()
            return True

    def set_flag(self, id_: str, field: str, value: bool) -> bool:
        """SET favorite/visited on a live row. True if a row changed."""
        if field not in _SET_FLAG_FIELDS:
            raise ValueError(f"Unsupported flag field: {field!r}")
        with self._sf() as s:
            row = s.scalars(
                select(SavedPlaceRow).where(
                    SavedPlaceRow.id == id_, SavedPlaceRow.deleted_at.is_(None)
                )
            ).first()
            if row is None:
                return False
            setattr(row, field, bool(value))
            s.commit()
            return True

    def find_duplicate(
        self,
        *,
        name: str,
        city: str | None,
        lat: float | None,
        lng: float | None,
        radius_km: float,
    ) -> SavedPlace | None:
        """Return a non-deleted same-name duplicate, or None.

        Same case-insensitive name AND either: both records have coordinates
        and are within ``radius_km`` (haversine), or coordinates are missing
        on either side and ``city`` matches.
        """
        with self._sf() as s:
            # Materialize to Pydantic INSIDE the session — never iterate ORM
            # rows after the block closes (detached-instance hazard).
            cands = [
                _row_to_saved_place(r)
                for r in s.scalars(
                    select(SavedPlaceRow).where(
                        SavedPlaceRow.deleted_at.is_(None),
                        func.lower(SavedPlaceRow.name) == func.lower(name),
                    )
                ).all()
            ]
        for cand in cands:
            both = (
                lat is not None
                and lng is not None
                and cand.latitude is not None
                and cand.longitude is not None
            )
            if both:
                if haversine_km(lat, lng, cand.latitude, cand.longitude) <= radius_km:
                    return cand
            elif cand.city == city:
                return cand
        return None
