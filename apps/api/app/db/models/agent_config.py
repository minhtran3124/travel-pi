"""AgentConfig ORM model — per-agent LLM provider/model/base_url override."""

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class AgentConfig(UUIDBase):
    __tablename__ = "agent_config"

    agent_name: Mapped[str] = mapped_column(String, nullable=False)
    provider: Mapped[str | None] = mapped_column(String, default=None)
    model: Mapped[str | None] = mapped_column(String, default=None)
    base_url: Mapped[str | None] = mapped_column(String, default=None)

    __table_args__ = (Index("ix_agent_config_agent_name", "agent_name", unique=True),)
