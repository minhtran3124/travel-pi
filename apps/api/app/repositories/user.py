"""User repository — tier lookup and upsert (specs/runtime-context-config B.1).

Tier is BE-resolved only; it is never accepted from the request body. The
default "free" is returned when no row exists, so callers never need to handle
a missing-user case for capability resolution.
"""

import logging

from app.db import models
from app.repositories.base import Repo

logger = logging.getLogger(__name__)


class UserRepository(Repo):
    """ORM-backed store for per-user profile data (currently: tier)."""

    def get_tier(self, user_id: str) -> str:
        """Return the stored tier for *user_id*, or ``"free"`` if no row exists."""
        with self._session() as s:
            row = s.get(models.User, user_id)
            return row.tier if row is not None else "free"

    def upsert_tier(self, user_id: str, tier: str) -> None:
        """Insert or update the tier for *user_id*."""
        with self._session() as s:
            row = s.get(models.User, user_id)
            if row is None:
                s.add(models.User(user_id=user_id, tier=tier))
            else:
                row.tier = tier
            self._commit(s)
            logger.info(
                "[UserRepository] upsert_tier user_id=%s tier=%s", user_id, tier
            )
