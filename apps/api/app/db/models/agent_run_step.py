"""AgentRunStep ORM model — one row per step of an agent turn, in ``seq`` order.

No user content may reach a step row: ``meta`` accepts only a scalar allowlist and
``error_type`` is ``type(exc).__name__``, never ``str(exc)``.
"""

from sqlalchemy import JSON, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class AgentRunStep(UUIDBase):
    __tablename__ = "agent_run_steps"

    run_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    node: Mapped[str | None] = mapped_column(String, nullable=True)
    ns: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    prompts: Mapped[list | None] = mapped_column(JSON, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    offset_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
