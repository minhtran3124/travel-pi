"""Best-effort ``agent_runs`` recorder for the SSE stream.

Async pass-through that yields every SSE event unchanged while, on stream
exhaustion, closing the turn's ``agent_runs`` row with a status derived from the
events seen (``interrupt`` → ``interrupted``, ``error`` or exception/cancellation
→ ``failed``, else ``completed``). Uses an isolated ``session_factory``;
persistence is best-effort and never raised into the reply path. A
``CancelledError`` marks the row ``failed`` and is re-raised.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session, sessionmaker

from app.agents.prompt_map import enrich_steps
from app.core.pricing import estimate_cost
from app.core.streaming import TypedSSEEvent
from app.repositories.agent_run import AgentRunRepository

if TYPE_CHECKING:
    from app.agents.live_registry import LiveTurnHandler
    from app.agents.metrics import TurnMetricsHandler

logger = logging.getLogger(__name__)


async def record_agent_run(
    events_iter: AsyncIterator[TypedSSEEvent],
    *,
    run_id: str,
    metrics: TurnMetricsHandler,
    session_factory: sessionmaker[Session],
    prompt_versions: dict | None = None,
    live: LiveTurnHandler | None = None,
) -> AsyncIterator[TypedSSEEvent]:
    """Pass every SSE event through unchanged while closing the ``agent_runs`` row.

    Reads ``current_flow`` from the ``done`` payload (the only place a pass-through
    can observe it) and finalizes the row in a ``finally`` on an isolated session.
    """
    saw_interrupt = False
    saw_error = False
    current_flow: str | None = None
    raised = False

    try:
        async for event in events_iter:
            if event.event == "interrupt":
                saw_interrupt = True
            elif event.event == "error":
                saw_error = True
            elif event.event == "done":
                try:
                    current_flow = json.loads(event.data).get("current_flow")
                except (ValueError, KeyError):
                    current_flow = None
            yield event
    except BaseException:
        # Client disconnect (CancelledError) or a crash in the inner iterator:
        # mark the row failed, then re-raise so the runtime sees the cancellation.
        raised = True
        raise
    finally:
        if live is not None:
            live.finish()  # backstop: the turn leaves the live registry on every exit path
        if saw_interrupt:
            status = "interrupted"
        elif saw_error or raised:
            status = "failed"
        else:
            status = "completed"
        try:
            # A failed/cancelled turn never reaches the mapper's success-path
            # metrics block, so close and price here (no-ops if already done) — the
            # dashboard's latency/cost rollups must not exclude failed turns.
            metrics.close_if_open()
            if metrics.cost_usd is None:
                metrics.cost_usd = estimate_cost(metrics.snapshot()["by_model"])
        except Exception:  # noqa: BLE001 — metrics must never break the stream
            logger.debug("[record_agent_run] metrics finalize failed", exc_info=True)

        try:
            AgentRunRepository(session_factory).finish(
                run_id,
                status=status,
                current_flow=current_flow,
                finished_at=datetime.now(UTC).isoformat(),
                metrics=metrics.snapshot(),
                prompt_versions=prompt_versions,
            )
        except Exception as exc:  # noqa: BLE001 — best-effort; never raise into the stream
            logger.error(
                "[record_agent_run] failed to finish agent_run id=%s: %s", run_id, exc
            )

        try:
            # Steps are written here on the isolated factory alongside ``finish``,
            # never from a background task against a flushed-but-uncommitted row
            # (that deadlocked).
            AgentRunRepository(session_factory).add_steps(
                run_id, enrich_steps(metrics.steps(), prompt_versions)
            )
        except Exception as exc:  # noqa: BLE001 — best-effort; never raise into the stream
            logger.error(
                "[record_agent_run] failed to add steps for id=%s: %s", run_id, exc
            )
