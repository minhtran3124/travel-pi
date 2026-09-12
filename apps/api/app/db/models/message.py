"""Message ORM model — one turn in an agent conversation (specs/travel-agent)."""

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class Message(UUIDBase):
    __tablename__ = "messages"

    conversation_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False, default="")
    # Tool calls / structured payload for assistant or tool turns. JSON works on
    # both SQLite and Postgres via SQLAlchemy's generic JSON type.
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Links an assistant reply to the agent_runs row that produced it (plain
    # String, no FK — repo convention). NULL for user turns and pre-link history.
    agent_run_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
