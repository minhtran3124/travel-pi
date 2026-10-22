"""FeedbackEvent ORM model — one immutable row per feedback action.

Append-only: the effective rating of an assistant message is a fold over its events
ordered by ``(created_at, id)``. Only the traveller's own comment is stored, capped
at 500 characters by the service.
"""

from sqlalchemy import CheckConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class FeedbackEvent(UUIDBase):
    __tablename__ = "feedback_events"

    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    assistant_message_id: Mapped[str] = mapped_column(
        String, nullable=False, index=True
    )
    agent_run_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String, nullable=False)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String, nullable=True)
    comment: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    locale: Mapped[str | None] = mapped_column(String, nullable=True)
    client_event_id: Mapped[str] = mapped_column(String, nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String, nullable=False)
    supersedes_event_id: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "user_id", "client_event_id", name="uq_feedback_events_user_client_event"
        ),
        CheckConstraint(
            "rating IS NULL OR rating IN (-1, 1)", name="ck_feedback_events_rating"
        ),
        # Fold order per message.
        Index(
            "ix_feedback_events_assistant_message_id_created_at_id",
            "assistant_message_id",
            "created_at",
            "id",
        ),
        # Export / erasure by user.
        Index("ix_feedback_events_user_id_created_at", "user_id", "created_at"),
        # Aggregate sampling by rating.
        Index("ix_feedback_events_rating_created_at", "rating", "created_at"),
    )
