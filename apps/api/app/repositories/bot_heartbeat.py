"""Data-access for ``bot_heartbeats``: upsert one row per (instance, process), list live rows, prune stale ones."""

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.db import models
from app.repositories.base import Repo


class BotHeartbeatRepository(Repo):
    """Heartbeat rows keyed by ``(instance_id, pid)``; timestamps are ISO-8601 strings."""

    def upsert(
        self,
        *,
        instance_id: str,
        pid: int,
        role: str,
        host: str,
        started_at: str,
        last_seen: str,
        snapshot: dict[str, Any] | None = None,
    ) -> None:
        """Insert the row, or refresh ``last_seen``/``snapshot`` when it exists (idempotent)."""
        values = {
            "role": role,
            "host": host,
            "started_at": started_at,
            "last_seen": last_seen,
            "snapshot": snapshot or {},
        }
        with self._session() as s:
            if not self._update(s, instance_id, pid, values):
                try:
                    with s.begin_nested():
                        s.add(
                            models.BotHeartbeat(
                                instance_id=instance_id, pid=pid, **values
                            )
                        )
                        s.flush()
                except IntegrityError:
                    # A concurrent writer inserted the same key first; refresh it instead.
                    self._update(s, instance_id, pid, values)
            self._commit(s)

    @staticmethod
    def _update(s, instance_id: str, pid: int, values: dict[str, Any]) -> bool:
        row = s.get(models.BotHeartbeat, (instance_id, pid))
        if row is None:
            return False
        for key, value in values.items():
            setattr(row, key, value)
        s.flush()
        return True

    def list_live(self, since: str) -> list[models.BotHeartbeat]:
        """Rows seen at or after ``since``, ordered by instance then pid."""
        with self._session() as s:
            rows = (
                s.execute(
                    select(models.BotHeartbeat)
                    .where(models.BotHeartbeat.last_seen >= since)
                    .order_by(models.BotHeartbeat.instance_id, models.BotHeartbeat.pid)
                )
                .scalars()
                .all()
            )
            for row in rows:
                s.expunge(row)
            return list(rows)

    def prune(self, before: str) -> int:
        """Delete rows last seen before ``before``; returns the number removed."""
        with self._session() as s:
            result = s.execute(
                delete(models.BotHeartbeat).where(
                    models.BotHeartbeat.last_seen < before
                )
            )
            self._commit(s)
            return result.rowcount or 0

    def delete(self, instance_id: str, pid: int) -> None:
        """Remove one process's row (clean shutdown)."""
        with self._session() as s:
            s.execute(
                delete(models.BotHeartbeat).where(
                    models.BotHeartbeat.instance_id == instance_id,
                    models.BotHeartbeat.pid == pid,
                )
            )
            self._commit(s)
