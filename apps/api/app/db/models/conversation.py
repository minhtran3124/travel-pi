"""Conversation ORM model — one agent chat thread (specs/travel-agent).

A conversation groups the messages of a single agent session for UI listing and
audit. The live agent state (full message history + working state) is owned by
the LangGraph checkpointer keyed on ``thread_id``; this table is the durable,
queryable record alongside it. No FK (matches the repo's String-id convention,
e.g. expenses.trip_id) so it works identically on SQLite and Postgres.
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class Conversation(UUIDBase):
    __tablename__ = "conversations"

    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    trip_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    domain: Mapped[str | None] = mapped_column(String, nullable=True)
