"""Best-effort ``agent_runs`` recorder for the SSE stream (specs/agent-turn-metrics §4.5).

Sibling of ``persist_assistant_turn``: an async pass-through that yields every SSE
event unchanged while, on stream exhaustion, closing the turn's ``agent_runs`` row
with a status derived from the events it saw (``interrupt`` → ``interrupted``,
``error`` or an exception / cancellation → ``failed``, else ``completed``).

Uses an **isolated** ``session_factory`` (not the request-scoped session, which
may be torn down before the stream drains). Persistence is best-effort: a repo
failure is logged and never raised into the reply path. A ``CancelledError`` (or
any exception from the inner iterator) marks the row ``failed`` and is re-raised.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session, sessionmaker

from app.core.streaming import TypedSSEEvent
from app.repositories.agent_run import AgentRunRepository

if TYPE_CHECKING:
    from app.agents.metrics import TurnMetricsHandler

logger = logging.getLogger(__name__)


async def record_agent_run(
    events_iter: AsyncIterator[TypedSSEEvent],
    *,
    run_id: str,
    metrics: TurnMetricsHandler,
    session_factory: sessionmaker[Session],
) -> AsyncIterator[TypedSSEEvent]:
    """Pass every SSE event through unchanged while closing the ``agent_runs`` row.

    Tracks ``interrupt`` / ``error`` events and reads ``current_flow`` from the
    ``done`` event payload (the only place a pass-through can observe it). In a
    ``finally`` the run row is finalized via ``AgentRunRepository.finish`` on an
    isolated session; the status is ``interrupted`` if an interrupt event was
    seen, ``failed`` on an error event or when the inner iterator raised
    (including ``CancelledError``, which is re-raised), else ``completed``.

    :param events_iter: The upstream SSE event stream to pass through.
    :param run_id: The router-minted ``agent_runs`` id to finalize.
    :param metrics: The turn's ``TurnMetricsHandler`` (its ``snapshot()`` is stored).
    :param session_factory: Isolated sessionmaker used to write the row.
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
        if saw_interrupt:
            status = "interrupted"
        elif saw_error or raised:
            status = "failed"
        else:
            status = "completed"
        try:
            AgentRunRepository(session_factory).finish(
                run_id,
                status=status,
                current_flow=current_flow,
                finished_at=datetime.now(UTC).isoformat(),
                metrics=metrics.snapshot(),
            )
        except Exception as exc:  # noqa: BLE001 — best-effort; never raise into the stream
            logger.error(
                "[record_agent_run] failed to finish agent_run id=%s: %s", run_id, exc
            )
