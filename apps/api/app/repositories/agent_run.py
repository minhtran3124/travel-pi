"""Data-access for agent-run metrics. Persistence is best-effort — ``finish`` on an unknown id logs and returns rather than raising into the reply path. Rows carry aggregated metrics only, no message text or PII."""

import logging
from datetime import datetime

from sqlalchemy import func, select, update

from app.db import models
from app.repositories.base import Repo

logger = logging.getLogger(__name__)

#: Keys mapped onto ``agent_runs`` columns in ``finish``; ``total_tokens`` is intentionally absent (derivable, not stored).
_FINISH_METRIC_KEYS = (
    "llm_calls",
    "llm_errors",
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "latency_ms",
    "cost_usd",
    "by_model",
    "by_node",
)

# Re-applied here even though the handler allowlists meta keys — the content boundary shouldn't rest on one caller staying disciplined.
# ``resumed_from`` is an internal run id (never user content) stamped on a resume's first step so the chain of resumed runs is auditable.
_META_KEYS = frozenset({"finish_reason", "resumed_from", "rubric_status"})


def _sanitised(step: dict) -> dict:
    """Keep only known columns, and inside ``meta`` only allowlisted scalar keys."""
    out = {k: v for k, v in step.items() if k in _STEP_KEYS}
    meta = out.get("meta")
    if isinstance(meta, dict):
        out["meta"] = {
            k: v
            for k, v in meta.items()
            if k in _META_KEYS and isinstance(v, (str, int, float, bool, type(None)))
        } or None
    elif meta is not None:
        out["meta"] = None
    return out


_STEP_KEYS = frozenset(
    {
        "seq",
        "kind",
        "node",
        "ns",
        "model",
        "prompts",
        "input_tokens",
        "output_tokens",
        "cached_tokens",
        "cost_usd",
        "offset_ms",
        "ms",
        "status",
        "error_type",
        "tool_name",
        "meta",
    }
)


class AgentRunRepository(Repo):
    """ORM-backed store of per-turn agent metrics."""

    def start(
        self,
        id: str,
        *,
        user_id: str,
        conversation_id: str,
        thread_id: str,
        trip_id: str | None,
        channel: str,
        kind: str,
        started_at: str,
    ) -> None:
        """Insert a fresh ``running`` row; the ``id`` is router-minted so the caller can correlate the row with the in-flight turn."""
        row = models.AgentRun(
            id=id,
            user_id=user_id,
            conversation_id=conversation_id,
            thread_id=thread_id,
            trip_id=trip_id,
            channel=channel,
            kind=kind,
            status="running",
            started_at=started_at,
        )
        with self._session() as s:
            s.add(row)
            self._commit(s)

    def finish(
        self,
        id: str,
        *,
        status: str,
        current_flow: str | None,
        finished_at: str,
        metrics: dict,
        prompt_versions: dict | None = None,
    ) -> None:
        """Finalize a run: set terminal status and metrics. Unknown metric keys are ignored; a missing id is logged and skipped so persistence never raises into the reply path."""
        with self._session() as s:
            row = s.get(models.AgentRun, id)
            if row is None:
                logger.warning("agent_run finish: no row for id=%s", id)
                return
            row.status = status
            row.current_flow = current_flow
            row.finished_at = finished_at
            for key in _FINISH_METRIC_KEYS:
                if key in metrics:
                    setattr(row, key, metrics[key])
            if prompt_versions is not None:
                row.prompt_versions = prompt_versions
            self._commit(s)

    def add_steps(self, run_id: str, steps: list[dict]) -> None:
        """Bulk-insert a run's steps. Unknown keys are ignored and there is no existence check on *run_id* — a step write for a missing run inserts orphans rather than raising into the reply path."""
        if not steps:
            return
        rows = [
            models.AgentRunStep(
                run_id=run_id,
                **_sanitised(step),
            )
            for step in steps
        ]
        with self._session() as s:
            s.add_all(rows)
            self._commit(s)

    def steps_for(self, run_id: str) -> list[models.AgentRunStep]:
        stmt = (
            select(models.AgentRunStep)
            .where(models.AgentRunStep.run_id == run_id)
            .order_by(models.AgentRunStep.seq)
        )
        with self._session() as s:
            return list(s.scalars(stmt).all())

    def add_background(
        self,
        id: str,
        *,
        llm_calls: int,
        tokens: int,
        ms: int,
        cost_usd: float | None = None,
        by_model: dict | None = None,
    ) -> None:
        """Add post-turn (background) LLM work onto the run row. ``cost_usd`` and ``by_model`` fold the spend into the turn's totals so cost reporting is not blind to it."""
        with self._session() as s:
            row = s.get(models.AgentRun, id)
            if row is None:
                logger.warning("agent_run add_background: no row for id=%s", id)
                return
            row.background_llm_calls += llm_calls
            row.background_tokens += tokens
            row.background_ms += ms
            if cost_usd is not None:
                row.cost_usd = (row.cost_usd or 0.0) + cost_usd
            if by_model:
                merged = {k: dict(v) for k, v in (row.by_model or {}).items()}
                for model, usage in by_model.items():
                    slot = merged.setdefault(model, {})
                    for field, value in usage.items():
                        slot[field] = slot.get(field, 0) + value
                row.by_model = merged
            self._commit(s)

    def list_recent(self, limit: int = 100) -> list[models.AgentRun]:
        stmt = (
            select(models.AgentRun)
            .order_by(models.AgentRun.created_at.desc())
            .limit(limit)
        )
        with self._session() as s:
            return list(s.scalars(stmt).all())

    def totals(self, since: datetime) -> dict:
        """Aggregate turns, tokens, cost and latencies since *since* (ISO-8601 strings sort chronologically, so a ``>=`` string compare is a correct cutoff)."""
        cutoff = since.isoformat()
        stmt = select(
            models.AgentRun.input_tokens,
            models.AgentRun.output_tokens,
            models.AgentRun.cost_usd,
            models.AgentRun.latency_ms,
        ).where(models.AgentRun.created_at >= cutoff)
        with self._session() as s:
            rows = s.execute(stmt).all()
        return {
            "turns": len(rows),
            "tokens": sum((r.input_tokens or 0) + (r.output_tokens or 0) for r in rows),
            "cost": sum(r.cost_usd for r in rows if r.cost_usd is not None),
            "latencies": [r.latency_ms for r in rows if r.latency_ms is not None],
        }

    def cost_rows_since(self, since: datetime) -> list:
        """Per-run cost columns for runs at or after *since* (same ISO string cutoff as ``totals``)."""
        cutoff = since.isoformat()
        stmt = select(
            models.AgentRun.created_at,
            models.AgentRun.input_tokens,
            models.AgentRun.output_tokens,
            models.AgentRun.cost_usd,
            models.AgentRun.by_model,
            models.AgentRun.background_tokens,
        ).where(models.AgentRun.created_at >= cutoff)
        with self._session() as s:
            return s.execute(stmt).all()

    def turn_cost_rows_since(self, since: datetime) -> list:
        """Per-run user, capability (``current_flow``) and cost columns for runs at or after *since* (same ISO string cutoff as ``totals``)."""
        cutoff = since.isoformat()
        stmt = select(
            models.AgentRun.user_id,
            models.AgentRun.current_flow,
            models.AgentRun.created_at,
            models.AgentRun.cost_usd,
            models.AgentRun.input_tokens,
            models.AgentRun.output_tokens,
            models.AgentRun.background_tokens,
        ).where(models.AgentRun.created_at >= cutoff)
        with self._session() as s:
            return s.execute(stmt).all()

    def llm_steps_since(self, since: datetime) -> list[models.AgentRunStep]:
        """Return ``llm`` steps created at or after *since*, oldest first (tool/node steps carry no cache tokens)."""
        cutoff = since.isoformat()
        stmt = (
            select(models.AgentRunStep)
            .where(models.AgentRunStep.kind == "llm")
            .where(models.AgentRunStep.created_at >= cutoff)
            .order_by(models.AgentRunStep.created_at)
        )
        with self._session() as s:
            return list(s.scalars(stmt).all())

    def get(self, run_id: str) -> models.AgentRun | None:
        """The run row, or ``None`` if unknown."""
        with self._session() as s:
            return s.get(models.AgentRun, run_id)

    def latest_for_trip(
        self,
        trip_id: str,
        kind: str,
    ) -> models.AgentRun | None:
        """The trip's most recent run of *kind*, newest ``created_at`` first, or ``None``."""
        stmt = (
            select(models.AgentRun)
            .where(models.AgentRun.trip_id == trip_id, models.AgentRun.kind == kind)
            .order_by(models.AgentRun.created_at.desc())
        )
        with self._session() as s:
            return s.scalars(stmt).first()

    def running_for(
        self,
        trip_id: str,
        kind: str,
    ) -> models.AgentRun | None:
        """The trip's first ``running`` run of *kind*, or ``None``."""
        stmt = select(models.AgentRun).where(
            models.AgentRun.trip_id == trip_id,
            models.AgentRun.kind == kind,
            models.AgentRun.status == "running",
        )
        with self._session() as s:
            return s.scalars(stmt).first()

    def count_for_trip(
        self,
        trip_id: str,
        kind: str,
        *,
        upto: str | None = None,
    ) -> int:
        """Count the trip's runs of *kind*, bounded to ``created_at <= upto`` when given."""
        stmt = (
            select(func.count())
            .select_from(models.AgentRun)
            .where(models.AgentRun.trip_id == trip_id, models.AgentRun.kind == kind)
        )
        if upto is not None:
            stmt = stmt.where(models.AgentRun.created_at <= upto)
        with self._session() as s:
            return int(s.scalar(stmt) or 0)

    def sweep_running_before(
        self,
        kind: str,
        cutoff: str,
    ) -> int:
        """Flip *kind* rows still ``running`` with ``started_at < cutoff`` to ``interrupted``; return the row count."""
        stmt = (
            update(models.AgentRun)
            .where(
                models.AgentRun.kind == kind,
                models.AgentRun.status == "running",
                models.AgentRun.started_at < cutoff,
            )
            .values(status="interrupted")
        )
        with self._session() as s:
            result = s.execute(stmt)
            self._commit(s)
            return int(result.rowcount or 0)
