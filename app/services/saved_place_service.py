"""Business rules for saved places — ID generation, 404/409s, dedup policy.

Mirrors the **trips** factory-DI pattern (module singleton + ``get_*``
factory + an ``Annotated`` dependency alias) so tests can override the
dependency onto a temp-DB instance via ``app.dependency_overrides``.
"""

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends

from app.core.config import get_settings
from app.crud.saved_place import SavedPlaceRepository
from app.db.engine import get_session_factory
from app.exceptions import ConflictError, NotFoundError
from app.schemas.saved_place import SavedPlace, SavedPlaceCreate

_DEDUP_RADIUS_KM = 0.05  # ~50 m


class SavedPlaceService:
    def __init__(self, database_url: str) -> None:
        self._repo = SavedPlaceRepository(get_session_factory(database_url))

    def init_db(self) -> None:
        self._repo.init_db()

    def create(self, request: SavedPlaceCreate) -> SavedPlace:
        dup = self._repo.find_duplicate(
            name=request.name,
            city=request.city,
            lat=request.latitude,
            lng=request.longitude,
            radius_km=_DEDUP_RADIUS_KM,
        )
        if dup is not None:
            raise ConflictError(
                f"A saved place named {request.name!r} already exists nearby.",
                hint=f"Reuse {dup.short_code} (id {dup.id}) instead of creating a duplicate.",
            )
        sp = SavedPlace(
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc).isoformat(),
            **request.model_dump(),
        )
        return self._repo.add(sp)

    def get(self, id_: str) -> SavedPlace:
        sp = self._repo.get(id_)
        if sp is None:
            raise NotFoundError(
                f"Saved place {id_!r} not found",
                hint="Use GET /places/saved to list saved places.",
            )
        return sp

    def list(self, **filters) -> list[SavedPlace]:
        return self._repo.list(**filters)

    def delete(self, id_: str) -> None:
        # Resolve to the canonical UUID first: id_ may be an SPL- short code,
        # but the repo writes match on `id` (UUIDs only).
        sp = self.get(id_)  # 404 if missing/already-deleted
        self._repo.soft_delete(sp.id, when=datetime.now(timezone.utc).isoformat())

    def set_flag(self, id_: str, field: str, value: bool) -> SavedPlace:
        sp = self.get(id_)  # resolves SPL- short code → UUID
        self._repo.set_flag(sp.id, field, value)
        return self.get(sp.id)


# Shared singleton — constructed at import time (cheap: builds a session
# factory). Tables are created later from the app's lifespan handler.
_saved_place_service = SavedPlaceService(get_settings().database_url)


def get_saved_place_service() -> SavedPlaceService:
    """FastAPI dependency returning the shared saved-place store."""
    return _saved_place_service


SavedPlaceDep = Annotated[SavedPlaceService, Depends(get_saved_place_service)]
