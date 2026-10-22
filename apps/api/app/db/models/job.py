"""Job ORM model — long-running agent work, transitioning pending -> running -> succeeded|failed for poll/SSE status."""

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase
from app.enums import JobStatus


class Job(UUIDBase):
    __tablename__ = "jobs"

    kind: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=JobStatus.PENDING.value
    )
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
