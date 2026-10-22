"""Data-access layer for saved places; business rules live in services/saved_place_service.py. Soft-delete filtered from reads."""

from sqlalchemy import func, select

from app.core.geo import haversine_km
from app.db import models
from app.db.base import Base
from app.repositories.base import Repo
from app.schemas.saved_place import SavedPlace

_SET_FLAG_FIELDS = {"favorite", "visited"}


def _row_to_saved_place(row: models.SavedPlace) -> SavedPlace:
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


class SavedPlaceRepository(Repo):
    """ORM-backed store of saved_places rows."""

    def init_db(self) -> None:
        Base.metadata.create_all(self._bind(), checkfirst=True)

    def add(self, sp: SavedPlace, user_id: str) -> SavedPlace:
        row = models.SavedPlace(
            id=sp.id,
            user_id=user_id,
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
        with self._session() as s:
            s.add(row)
            self._commit(s)
        return sp

    def get(self, id_: str, user_id: str | None = None) -> SavedPlace | None:
        """Fetch a live saved place by raw UUID or SPL- short code (short codes are derived, so a code lookup scans and compares). When ``user_id`` is given, a foreign owner's row is indistinguishable from missing; ``None`` is an UNSCOPED lookup — a footgun for trusted internal callers only, never on an id an untrusted caller can influence."""
        owner = (models.SavedPlace.user_id == user_id,) if user_id is not None else ()
        with self._session() as s:
            row = s.scalars(
                select(models.SavedPlace).where(
                    models.SavedPlace.id == id_,
                    *owner,
                    models.SavedPlace.deleted_at.is_(None),
                )
            ).first()
            if row is not None:
                return _row_to_saved_place(row)
            rows = s.scalars(
                select(models.SavedPlace).where(
                    *owner,
                    models.SavedPlace.deleted_at.is_(None),
                )
            ).all()
            wanted = id_.upper()
            for r in rows:
                sp = _row_to_saved_place(r)
                if sp.short_code.upper() == wanted:
                    return sp
        return None

    def list(
        self,
        user_id: str,
        *,
        city: str | None = None,
        category: str | None = None,
        favorite: bool | None = None,
        visited: bool | None = None,
    ) -> list[SavedPlace]:
        stmt = select(models.SavedPlace).where(
            models.SavedPlace.user_id == user_id,
            models.SavedPlace.deleted_at.is_(None),
        )
        if city is not None:
            stmt = stmt.where(func.lower(models.SavedPlace.city) == func.lower(city))
        if category is not None:
            stmt = stmt.where(
                func.lower(models.SavedPlace.category) == func.lower(category)
            )
        if favorite is not None:
            stmt = stmt.where(models.SavedPlace.favorite == bool(favorite))
        if visited is not None:
            stmt = stmt.where(models.SavedPlace.visited == bool(visited))
        stmt = stmt.order_by(
            models.SavedPlace.created_at.desc(), models.SavedPlace.id.desc()
        )
        with self._session() as s:
            return [_row_to_saved_place(r) for r in s.scalars(stmt).all()]

    def soft_delete(self, id_: str, user_id: str, *, when: str) -> bool:
        """Stamp ``deleted_at`` on a live saved place (soft delete); another owner's row is a no-op."""
        with self._session() as s:
            row = s.scalars(
                select(models.SavedPlace).where(
                    models.SavedPlace.id == id_,
                    models.SavedPlace.user_id == user_id,
                    models.SavedPlace.deleted_at.is_(None),
                )
            ).first()
            if row is None:
                return False
            row.deleted_at = when
            self._commit(s)
            return True

    def set_flag(self, id_: str, user_id: str, field: str, value: bool) -> bool:
        """Set favorite/visited on a live row; another owner's row is a no-op."""
        if field not in _SET_FLAG_FIELDS:
            raise ValueError(f"Unsupported flag field: {field!r}")
        with self._session() as s:
            row = s.scalars(
                select(models.SavedPlace).where(
                    models.SavedPlace.id == id_,
                    models.SavedPlace.user_id == user_id,
                    models.SavedPlace.deleted_at.is_(None),
                )
            ).first()
            if row is None:
                return False
            setattr(row, field, bool(value))
            self._commit(s)
            return True

    def find_duplicate(
        self,
        *,
        user_id: str,
        name: str,
        city: str | None,
        lat: float | None,
        lng: float | None,
        radius_km: float,
    ) -> SavedPlace | None:
        """Return a non-deleted same-name duplicate scoped to the caller, or None — a coordinate match within ``radius_km`` (haversine), else a city match when coordinates are missing."""
        with self._session() as s:
            # Materialize inside the session — iterating ORM rows after the block closes is a detached-instance hazard.
            cands = [
                _row_to_saved_place(r)
                for r in s.scalars(
                    select(models.SavedPlace).where(
                        models.SavedPlace.user_id == user_id,
                        models.SavedPlace.deleted_at.is_(None),
                        func.lower(models.SavedPlace.name) == func.lower(name),
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
