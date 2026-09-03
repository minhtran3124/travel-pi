"""Data-access for agent-run metrics (specs/agent-turn-metrics).

ORM persistence only. Persistence is best-effort: ``finish`` on an unknown id
logs a warning and returns rather than raising into the reply path. Rows carry
aggregated token / cost / latency metrics only — no message text, tool args, or PII.
"""

import logging
from datetime import datetime

from sqlalchemy import select

from app.db import models
from app.repositories.base import Repo

logger = logging.getLogger(__name__)

#: Snapshot keys that map directly onto an ``agent_runs`` column in ``finish``.
#: ``total_tokens`` is intentionally absent (derivable, not stored); any other
#: unknown key is ignored.
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

#: Columns of ``agent_run_steps`` an ``add_steps`` payload may set. Any other key
#: in a step dict is ignored, so a caller can pass a superset without raising.
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
        """Insert a fresh ``running`` row for a starting turn.

        The ``id`` is minted by the router (never generated here) so the caller
        can correlate the row with the in-flight turn before it finishes.

        :param id: The router-minted run id (primary key).
        :param user_id: The effective owner's id.
        :param conversation_id: The conversation this turn belongs to.
        :param thread_id: The LangGraph thread key.
        :param trip_id: The associated trip id, if any.
        :param channel: ``chat`` or ``stream``.
        :param kind: ``turn`` or ``resume``.
        :param started_at: ISO-8601 start timestamp.
        """
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
        """Finalize a run: set terminal status and the accumulated metrics.

        Maps the known snapshot keys of *metrics* onto columns; unknown keys
        (e.g. ``total_tokens``) are ignored. A missing id is logged and skipped
        so metric persistence never raises into the reply path.

        :param id: The run id set at ``start``.
        :param status: Terminal status (``completed`` / ``interrupted`` / ``failed``).
        :param current_flow: The final flow, if any.
        :param finished_at: ISO-8601 finish timestamp.
        :param metrics: The turn's metric snapshot.
        :param prompt_versions: Mapping of prompt name to the version the turn used;
            ``None`` leaves the stored value unchanged.
        """
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
        """Bulk-insert the per-step call chain of a run.

        Unknown keys in a step dict are ignored (the same tolerance ``finish``
        applies to its metric snapshot) and an empty list is a no-op. No
        existence check on *run_id*: steps are supplementary, so a step write for
        a missing run inserts orphan rows rather than raising into the reply path.

        :param run_id: The run these steps belong to.
        :param steps: Step payloads; keys outside the step columns are dropped.
        """
        if not steps:
            return
        rows = [
            models.AgentRunStep(
                run_id=run_id,
                **{k: v for k, v in step.items() if k in _STEP_KEYS},
            )
            for step in steps
        ]
        with self._session() as s:
            s.add_all(rows)
            self._commit(s)

    def steps_for(self, run_id: str) -> list[models.AgentRunStep]:
        """Return a run's steps in ``seq`` order.

        :param run_id: The run whose steps to load.
        :return: The run's ``AgentRunStep`` rows ordered by ``seq`` ascending.
        """
        stmt = (
            select(models.AgentRunStep)
            .where(models.AgentRunStep.run_id == run_id)
            .order_by(models.AgentRunStep.seq)
        )
        with self._session() as s:
            return list(s.scalars(stmt).all())

    def add_background(self, id: str, *, llm_calls: int, tokens: int, ms: int) -> None:
        """Increment the background metric columns after the response is sent.

        :param id: The run id set at ``start``.
        :param llm_calls: Background LLM calls to add.
        :param tokens: Background tokens to add.
        :param ms: Background wall-clock milliseconds to add.
        """
        with self._session() as s:
            row = s.get(models.AgentRun, id)
            if row is None:
                logger.warning("agent_run add_background: no row for id=%s", id)
                return
            row.background_llm_calls += llm_calls
            row.background_tokens += tokens
            row.background_ms += ms
            self._commit(s)

    def list_recent(self, limit: int = 100) -> list[models.AgentRun]:
        """Return the most recent runs, newest first.

        :param limit: Maximum number of rows to return.
        :return: A list of ``AgentRun`` rows ordered newest-first.
        """
        stmt = (
            select(models.AgentRun)
            .order_by(models.AgentRun.created_at.desc())
            .limit(limit)
        )
        with self._session() as s:
            return list(s.scalars(stmt).all())

    def totals(self, since: datetime) -> dict:
        """Aggregate turns, tokens, cost and latencies since *since*.

        Filters on ``created_at`` (always populated) — ISO-8601 strings sort
        chronologically, so a ``>=`` string comparison is a correct cutoff.

        :param since: Only runs created at or after this instant are counted.
        :return: ``{turns, tokens, cost, latencies}`` where ``tokens`` sums
            input + output, ``cost`` sums non-null ``cost_usd``, and
            ``latencies`` is the list of non-null ``latency_ms`` values.
        """
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
