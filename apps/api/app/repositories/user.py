"""User repository: tier lookup and upsert. Tier is BE-resolved only, never from the request body; a missing user resolves to "free"."""

import logging

from app.db import models
from app.enums import Tier
from app.repositories.base import Repo

logger = logging.getLogger(__name__)


class UserRepository(Repo):
    """ORM-backed store for per-user profile data (currently: tier, stored as a plain string)."""

    def get_tier(self, user_id: str) -> str:
        """Return the stored tier for *user_id*, or ``"free"`` if no row exists."""
        with self._session() as s:
            row = s.get(models.User, user_id)
            return row.tier if row is not None else Tier.FREE.value

    def ensure_user(self, user_id: str, default_tier: str = Tier.FREE.value) -> None:
        """Insert a ``User`` row for *user_id* with *default_tier* if absent; no-op otherwise."""
        with self._session() as s:
            if s.get(models.User, user_id) is None:
                s.add(models.User(user_id=user_id, tier=default_tier))
                self._commit(s)
                logger.info("[UserRepository] ensure_user created user_id=%s", user_id)

    def exists(self, user_id: str) -> bool:
        with self._session() as s:
            return s.get(models.User, user_id) is not None

    def upsert_tier(self, user_id: str, tier: str) -> None:
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
