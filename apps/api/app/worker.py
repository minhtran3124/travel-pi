"""Arq worker: runs research and memory extraction off the web process.

Start with ``arq app.worker.WorkerSettings`` (needs ``REDIS_URL``). The web process
only enqueues (``app/core/queue.py``); this process owns the long jobs, so a web
deploy or crash no longer kills them.

Idempotency, keyed by ``run_id``:

* The web enqueues each job under a deterministic job id (``run_id`` /
  ``memory:<run_id>``), so Arq drops a duplicate enqueue.
* ``run_research`` only drives a run whose row is still ``running``; a replay
  after the row went terminal is a no-op.
* ``max_tries = 1``: Arq never auto-retries a job, which would replay a research
  turn over its checkpointed thread or double-count background metrics. A job lost
  with Redis or a killed worker leaves a ``running`` row that
  ``ResearchService.sweep_stale`` flips to ``interrupted`` (at worker start and
  every 5 minutes via cron).

Jobs take a plain ``ctx`` dict (``service``, ``bus``, ``store``, ``llm``,
``session_factory``) filled by :func:`startup`, so they are testable without Redis.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from typing import Any

from arq import cron
from arq.connections import RedisSettings
from arq.worker import func
from langchain_core.messages import messages_from_dict

from app.core.config import get_settings
from app.memory.extraction_runner import run_memory_extraction

logger = logging.getLogger(__name__)

_RUNNING = "running"


async def run_research(
    ctx: dict[str, Any],
    run_id: str,
    user_id: str,
    trip_id: str,
    instruction: str | None = None,
    language: str | None = None,
    origin: str | None = None,
    resumed_from: str | None = None,
) -> None:
    """Drive one booked research run to a terminal state. Never raises (the runner
    folds every failure into the run row)."""
    service = ctx["service"]
    run = service.status(run_id)
    if run is None or run.status != _RUNNING:
        logger.info(
            "[worker] run_research run=%s skipped (%s)",
            run_id,
            "unknown" if run is None else run.status,
        )
        return
    if not service.runnable:
        logger.warning("[worker] run_research run=%s: no research agent", run_id)
        return
    # The web opens the run on its own bus; the runner publishes to this process's.
    ctx["bus"].open(run_id)
    await service.launch(
        run_id,
        user_id,
        trip_id,
        instruction=instruction,
        language=language,
        origin=origin,
        resumed_from=resumed_from,
    )


async def run_memory_extraction_job(
    ctx: dict[str, Any],
    run_id: str,
    messages: list[dict],
    user_id: str,
    trip_id: str | None,
    plan_approved: bool,
) -> None:
    """Run post-turn memory extraction for ``run_id`` (best-effort, never raises).
    The web only enqueues turns whose memory writes are allowed."""
    await asyncio.to_thread(
        run_memory_extraction,
        messages=messages_from_dict(messages),
        user_id=user_id,
        trip_id=trip_id,
        plan_approved=plan_approved,
        allow_memory_write=True,
        store=ctx["store"],
        llm=ctx["llm"],
        run_id=run_id,
        session_factory=ctx["session_factory"],
    )


async def startup(ctx: dict[str, Any]) -> None:
    """Open the shared backends and build the agents once per worker process."""
    from app.agents.checkpointer import open_checkpointer
    from app.agents.graph import build_graph
    from app.db.engine import get_session_factory
    from app.memory.store import open_store
    from app.research.progress import make_progress_bus
    from app.research.service import ResearchService

    settings = get_settings()
    stack = AsyncExitStack()
    checkpointer = await stack.enter_async_context(
        open_checkpointer(settings.database_url)
    )
    store = await stack.enter_async_context(open_store(settings.database_url))
    graph = build_graph(checkpointer=checkpointer, store=store)

    agent = None
    if settings.research_enabled:
        from app.research.agent import build_research_agent

        agent = build_research_agent(store=store, checkpointer=checkpointer)

    session_factory = get_session_factory(settings.database_url)
    bus = make_progress_bus()
    service = ResearchService(
        session_factory=session_factory, store=store, agent=agent, bus=bus
    )
    # Safety net for runs a previous (killed) worker left ``running``.
    service.sweep_stale()
    ctx.update(
        stack=stack,
        store=store,
        llm=graph.extract_memory_llm,
        session_factory=session_factory,
        bus=bus,
        service=service,
    )
    logger.info("[worker] ready: research=%s", "on" if agent is not None else "off")


async def shutdown(ctx: dict[str, Any]) -> None:
    stack = ctx.get("stack")
    if stack is not None:
        await stack.aclose()


async def sweep_stale_job(ctx: dict[str, Any]) -> None:
    """Periodic recovery: flip runs stuck ``running`` past the stale window (e.g.
    enqueued while no worker was consuming) to ``interrupted``."""
    swept = await asyncio.to_thread(ctx["service"].sweep_stale)
    if swept:
        logger.info("[worker] swept %s stale research run(s)", swept)


class WorkerSettings:
    functions = [
        run_research,
        func(run_memory_extraction_job, name="run_memory_extraction"),
    ]
    # Every 5 minutes, not only at startup.
    cron_jobs = [
        cron(sweep_stale_job, minute=set(range(0, 60, 5)), run_at_startup=False)
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(
        get_settings().redis_url or "redis://localhost:6379"
    )
    max_tries = 1
    # Room for the research timeout plus finalisation; the runner enforces the real bound.
    job_timeout = get_settings().research_timeout_s + 120
    # Research holds a job for minutes; a few at once per worker, not the arq default of 10.
    max_jobs = 4
    # Keep results long enough that a duplicate enqueue by run_id is dropped.
    keep_result = 3600
