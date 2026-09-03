"""AgentRun ORM model — one durable record per agent turn (specs/agent-turn-metrics).

Each row captures the token / cost / latency snapshot of a single agent turn (or a
HITL resume): who ran it, on which conversation and thread, and the aggregated LLM
usage the turn accumulated. The live agent state stays with the LangGraph
checkpointer keyed on ``thread_id``; this table is the queryable metrics record
alongside it. No FK (matches the repo's String-id convention) so it behaves
identically on SQLite and Postgres.

Metric collection is best-effort: nothing on the reply path may raise because a
column here failed to populate. No message text, tool args, or PII is stored.
"""

from sqlalchemy import JSON, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UUIDBase


class AgentRun(UUIDBase):
    __tablename__ = "agent_runs"

    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    conversation_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    thread_id: Mapped[str] = mapped_column(String, nullable=False)
    trip_id: Mapped[str | None] = mapped_column(String, nullable=True)
    channel: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    current_flow: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at: Mapped[str | None] = mapped_column(String, nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    by_model: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    by_node: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    background_llm_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    background_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    background_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
