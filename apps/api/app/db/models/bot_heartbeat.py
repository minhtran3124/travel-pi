"""Bot heartbeat ORM model — one row per (instance, process), upserted by a background task.

``snapshot`` carries the process's in-flight agent registry; ``last_seen`` decides liveness.
"""

from typing import Any

from sqlalchemy import JSON, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BotHeartbeat(Base):
    __tablename__ = "bot_heartbeats"

    instance_id: Mapped[str] = mapped_column(String, primary_key=True)
    pid: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    role: Mapped[str] = mapped_column(String, nullable=False, default="web")
    host: Mapped[str] = mapped_column(String, nullable=False, default="")
    started_at: Mapped[str] = mapped_column(String, nullable=False)
    last_seen: Mapped[str] = mapped_column(String, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    __table_args__ = (Index("ix_bot_heartbeats_last_seen", "last_seen"),)
