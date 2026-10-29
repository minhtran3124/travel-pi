"""Bot heartbeat task — upserts this process's ``bot_heartbeats`` row every few seconds.

Runs as a background asyncio task with its own short-lived sessions (never a request
session); every DB call goes through ``asyncio.to_thread`` so a slow database delays only
the heartbeat. Failures are logged and swallowed. The snapshot comes from a plain provider
hook (``set_snapshot_provider``) that defaults to ``{}``; the live agent registry plugs in
there. A worker entrypoint calls ``start_heartbeat(role="worker")``.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.instance import BotIdentity, resolve_identity
from app.db.engine import get_session_factory
from app.repositories.bot_heartbeat import BotHeartbeatRepository

logger = logging.getLogger(__name__)

SnapshotProvider = Callable[[], dict[str, Any]]

# Rows untouched for this long belong to dead processes; pruned opportunistically.
PRUNE_AFTER = timedelta(hours=1)
PRUNE_EVERY_BEATS = 20
STOP_TIMEOUT_SECONDS = 2.0

_snapshot_provider: SnapshotProvider = dict


def set_snapshot_provider(provider: SnapshotProvider | None) -> None:
    """Register the callable whose return value is stored as the heartbeat ``snapshot`` (None restores ``{}``)."""
    global _snapshot_provider
    _snapshot_provider = provider or dict


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds")


class Heartbeat:
    """One process's heartbeat loop; ``beat_once`` is the synchronous unit of work."""

    def __init__(
        self,
        identity: BotIdentity,
        session_factory: "sessionmaker[Session]",
        interval_seconds: float,
    ) -> None:
        self.identity = identity
        self._repo = BotHeartbeatRepository(session_factory)
        self._interval = interval_seconds
        self._task: asyncio.Task | None = None
        self._beats = 0
        self._failure_logged = False

    def beat_once(self) -> bool:
        """Upsert the row (and occasionally prune); returns False when the write failed."""
        now = datetime.now(timezone.utc)
        try:
            try:
                snapshot = _snapshot_provider()
            except Exception:
                logger.exception("Heartbeat snapshot provider failed; sending {}")
                snapshot = {}
            self._repo.upsert(
                instance_id=self.identity.instance_id,
                pid=self.identity.pid,
                role=self.identity.role,
                host=self.identity.host,
                started_at=self.identity.started_at,
                last_seen=_iso(now),
                snapshot=snapshot,
            )
            self._beats += 1
            if self._beats % PRUNE_EVERY_BEATS == 1:
                self._repo.prune(_iso(now - PRUNE_AFTER))
            self._failure_logged = False
            return True
        except Exception:
            # A deploy that skipped the migration must not take the API down: log once per outage, keep retrying.
            if not self._failure_logged:
                self._failure_logged = True
                logger.exception("Bot heartbeat write failed (table missing?)")
            return False

    async def _run(self) -> None:
        while True:
            await asyncio.to_thread(self.beat_once)
            await asyncio.sleep(self._interval)

    def start(self) -> None:
        """Start the loop on the running event loop (idempotent)."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="bot-heartbeat")

    async def stop(self) -> None:
        """Cancel the loop (short timeout) and remove this process's row; never raises."""
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await asyncio.wait_for(task, STOP_TIMEOUT_SECONDS)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception:
                logger.exception("Bot heartbeat task ended with an error")
        try:
            await asyncio.to_thread(
                self._repo.delete, self.identity.instance_id, self.identity.pid
            )
        except Exception:
            logger.exception("Could not remove bot heartbeat row on shutdown")


def start_heartbeat(
    role: str | None = None,
    session_factory: "sessionmaker[Session] | None" = None,
) -> Heartbeat | None:
    """Start this process's heartbeat; returns None when ``bot_heartbeat_enabled`` is off.

    Call from an async context (the web ``lifespan``, or a worker's startup hook with ``role="worker"``).
    """
    settings = get_settings()
    if not settings.bot_heartbeat_enabled:
        return None
    heartbeat = Heartbeat(
        resolve_identity(role),
        session_factory or get_session_factory(settings.database_url),
        settings.bot_heartbeat_interval_seconds,
    )
    heartbeat.start()
    return heartbeat
