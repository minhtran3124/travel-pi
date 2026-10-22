"""Message ORM model — one turn in an agent conversation."""

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class Message(UUIDBase):
    __tablename__ = "messages"

    conversation_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False, default="")
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Links an assistant reply to its agent_runs row; NULL for user turns and pre-link history.
    agent_run_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
