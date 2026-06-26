"""Job ORM model — long-running agent work (specs/travel-agent, llm-readiness 3.1).

The chosen async model is BackgroundTasks + a Job row + poll/SSE for status: an
agent run that may take a while writes a Job row, transitions
pending -> running -> succeeded|failed, and stashes its result/error for the
client to poll. Runtime state (not seeded).
"""

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
