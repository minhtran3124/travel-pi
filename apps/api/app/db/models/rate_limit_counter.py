"""Rate-limit counter ORM model — one fixed-window counter row per policy/subject/window.

``prune_after`` persists the window boundary plus a one-window clock-skew grace so
opportunistic cleanup can use an index.
"""

from sqlalchemy import BigInteger, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class RateLimitCounter(UUIDBase):
    __tablename__ = "rate_limit_counters"

    bucket: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    window_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    window_start: Mapped[int] = mapped_column(BigInteger, nullable=False)
    prune_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        # One row per policy/subject/window; also the lookup index for the atomic increment.
        UniqueConstraint(
            "bucket",
            "subject",
            "window_seconds",
            "window_start",
            name="uq_rate_limit_window",
        ),
        # Makes opportunistic pruning (bucket equality + expiry range) indexable.
        Index("ix_rate_limit_counters_bucket_prune_after", "bucket", "prune_after"),
    )
