"""Conversation ORM model — the durable, queryable record of one agent chat thread."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class Conversation(UUIDBase):
    __tablename__ = "conversations"

    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    trip_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    domain: Mapped[str | None] = mapped_column(String, nullable=True)
