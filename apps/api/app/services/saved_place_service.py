"""Business rules for saved places — ID generation, 404/409s, dedup policy.

Mirrors the **trips** factory-DI pattern (module singleton + ``get_*``
factory + an ``Annotated`` dependency alias) so tests can override the
dependency onto a temp-DB instance via ``app.dependency_overrides``.
"""

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, get_current_user
from app.core.config import get_settings
from app.db.engine import get_session_factory
from app.db.session import get_session
from app.exceptions import ConflictError, NotFoundError
from app.repositories.saved_place import SavedPlaceRepository
from app.schemas.saved_place import SavedPlace, SavedPlaceCreate

_DEDUP_RADIUS_KM = 0.05  # ~50 m


class SavedPlaceService:
    def __init__(self, session: Session, user_id: str) -> None:
        """Bind the store to one owner (#118).

        The owner is a property of the service instance rather than a parameter
        on every method: create/get/list/delete/set_flag all funnel the owner
        into the repository, so no future method can forget to scope its query.

        :param session: The request-scoped DB session.
        :param user_id: The caller who owns the saved places this instance may
            touch.
        """
        self._repo = SavedPlaceRepository(session)
        self._user_id = user_id

    def create(self, request: SavedPlaceCreate) -> SavedPlace:
        dup = self._repo.find_duplicate(
            user_id=self._user_id,
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
        return self._repo.add(sp, self._user_id)

    def get(self, id_: str) -> SavedPlace:
        sp = self._repo.get(id_, self._user_id)
        if sp is None:
            raise NotFoundError(
                f"Saved place {id_!r} not found",
                hint="Use GET /places/saved to list saved places.",
            )
        return sp

    def list(self, **filters) -> list[SavedPlace]:
        return self._repo.list(self._user_id, **filters)

    def delete(self, id_: str) -> None:
        # Resolve to the canonical UUID first: id_ may be an SPL- short code,
        # but the repo writes match on `id` (UUIDs only).
        sp = self.get(id_)  # 404 if missing/already-deleted/not the caller's
        self._repo.soft_delete(
            sp.id, self._user_id, when=datetime.now(timezone.utc).isoformat()
        )

    def set_flag(self, id_: str, field: str, value: bool) -> SavedPlace:
        sp = self.get(id_)  # resolves SPL- short code → UUID (owner-scoped)
        self._repo.set_flag(sp.id, self._user_id, field, value)
        return self.get(sp.id)


def init_db() -> None:
    """Create the saved_places table (startup; no request context)."""
    SavedPlaceRepository(get_session_factory(get_settings().database_url)).init_db()


def get_saved_place_service(
    session: Annotated[Session, Depends(get_session)],
    auth_user: Annotated[AuthUser, Depends(get_current_user)],
) -> SavedPlaceService:
    """FastAPI dependency: a saved-place store bound to the request session AND caller.

    ``get_current_user`` is the *required* variant, so every saved-place route
    depending on this now 401s without a valid token and is scoped to the
    caller's rows (#118). The public catalog routes do not depend on it and
    stay open.

    :param session: Request-scoped DB session.
    :param auth_user: The authenticated caller; supplies the owner filter.
    :return: A ``SavedPlaceService`` bound to the request session and caller.
    """
    return SavedPlaceService(session, auth_user.id)


SavedPlaceDep = Annotated[SavedPlaceService, Depends(get_saved_place_service)]
