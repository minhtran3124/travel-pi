"""Data-access for the DB-backed rate limiter; policy lives in app.core.rate_limit. Owns the atomic fixed-window increment (DB-level ``count = count + 1`` so concurrent workers can't under-count) and opportunistic pruning."""

from dataclasses import dataclass

from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import models
from app.db.base import _utc_now_iso
from app.repositories.base import Repo


@dataclass(frozen=True)
class RateLimitDecision:
    """The outcome of a single rate-limit hit."""

    allowed: bool
    remaining: int
    reset_at: int
    retry_after: int


class RateLimitRepository(Repo):
    """Atomic fixed-window counter over ``rate_limit_counters``."""

    def hit(
        self,
        *,
        bucket: str,
        subject: str,
        now_epoch: int,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        """Record one request and report whether it is within the limit."""
        window_start = now_epoch - (now_epoch % window_seconds)
        reset_at = window_start + window_seconds
        prune_after = window_start + (2 * window_seconds)
        with self._session() as s:
            # On SQLite, make a concurrent writer wait for the lock rather than raise "database is locked"; no-op on Postgres.
            if s.get_bind().dialect.name == "sqlite":
                s.execute(text("PRAGMA busy_timeout = 5000"))
            count, inserted = self._increment(
                s, bucket, subject, window_seconds, window_start, prune_after
            )
            if inserted:
                # Prune only when a NEW window is created (keeps the DELETE off the hot path), scoped to this bucket.
                s.execute(
                    delete(models.RateLimitCounter).where(
                        models.RateLimitCounter.bucket == bucket,
                        models.RateLimitCounter.prune_after <= now_epoch,
                    )
                )
            self._commit(s)
        allowed = count <= limit
        remaining = max(0, limit - count)
        retry_after = 0 if allowed else max(1, reset_at - now_epoch)
        return RateLimitDecision(
            allowed=allowed,
            remaining=remaining,
            reset_at=reset_at,
            retry_after=retry_after,
        )

    def _increment(
        self,
        s: Session,
        bucket: str,
        subject: str,
        window_seconds: int,
        window_start: int,
        prune_after: int,
    ) -> tuple[int, bool]:
        """Atomically add 1 to the window's counter; returns ``(new_count, inserted)`` where ``inserted`` gates the opportunistic prune."""
        upd = (
            update(models.RateLimitCounter)
            .where(
                models.RateLimitCounter.bucket == bucket,
                models.RateLimitCounter.subject == subject,
                models.RateLimitCounter.window_seconds == window_seconds,
                models.RateLimitCounter.window_start == window_start,
            )
            .values(
                count=models.RateLimitCounter.count + 1,
                updated_at=_utc_now_iso(),
            )
        )
        result = s.execute(upd)
        if result.rowcount and result.rowcount > 0:
            return self._read_count(
                s, bucket, subject, window_seconds, window_start
            ), False
        # No existing row for this window — insert the first hit race-safely.
        try:
            with s.begin_nested():
                s.add(
                    models.RateLimitCounter(
                        bucket=bucket,
                        subject=subject,
                        window_seconds=window_seconds,
                        window_start=window_start,
                        prune_after=prune_after,
                        count=1,
                    )
                )
                s.flush()
            return 1, True
        except IntegrityError:
            # A concurrent worker inserted the row first; increment it now.
            result = s.execute(upd)
            if result.rowcount and result.rowcount > 0:
                return self._read_count(
                    s, bucket, subject, window_seconds, window_start
                ), False
            # Defensive: the row vanished between the failed insert and this update (effectively unreachable given prune grace); treat as a fresh first hit rather than raising.
            return 1, False

    def _read_count(
        self,
        s: Session,
        bucket: str,
        subject: str,
        window_seconds: int,
        window_start: int,
    ) -> int:
        return s.execute(
            select(models.RateLimitCounter.count).where(
                models.RateLimitCounter.bucket == bucket,
                models.RateLimitCounter.subject == subject,
                models.RateLimitCounter.window_seconds == window_seconds,
                models.RateLimitCounter.window_start == window_start,
            )
        ).scalar_one()
