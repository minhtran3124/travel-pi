"""Rate-limit counter ORM model — one row per (bucket, subject, time window).

Backs the reusable, DB-backed rate limiter (``specs/rate-limit-primitive``).
A ``bucket`` names the policy (e.g. ``"feedback"``), ``subject`` is the effective
actor (JWT subject or anonymous id), and ``window_start`` is the fixed-window
boundary in epoch seconds. ``count`` is incremented atomically per request.

DB is the shared store, so enforcement is durable and correct across workers
without Redis. No FK (matches the repo's String-id convention) so it behaves
identically on SQLite and Postgres.
"""

from sqlalchemy import Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class RateLimitCounter(UUIDBase):
    __tablename__ = "rate_limit_counters"

    bucket: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    window_start: Mapped[int] = mapped_column(Integer, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        # One counter row per policy/subject/window. Also serves as the lookup
        # index for the atomic increment (leftmost-prefix on bucket, subject).
        UniqueConstraint(
            "bucket", "subject", "window_start", name="uq_rate_limit_window"
        ),
        # Prune expired windows cheaply.
        Index("ix_rate_limit_counters_window_start", "window_start"),
    )
