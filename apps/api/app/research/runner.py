"""Background driver for one trip-research turn (design §4).

Streams the compiled deep agent over its checkpointed thread, projects each
``astream_events(version="v3")`` item onto the progress bus, and finalises the
run row on an *isolated* session factory — the same shape the chat turn uses, but
off any request. Scheduled as a FastAPI ``BackgroundTask``; therefore it must
never let an exception escape. A timeout or any other failure is folded into a
``failed`` run row (with an error step carrying ``error_type``) and a terminal
``research_error`` bus event, so a caller polling the bus or the DB always sees a
terminal state.
"""

from __future__ import annotations

import asyncio
import logging
import time

from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import Session, sessionmaker

from app.agents.metrics import TurnMetricsHandler
from app.agents.prompt_map import enrich_steps
from app.core.config import get_settings
from app.core.languages import LANGUAGE_NAMES, normalize
from app.core.pricing import estimate_cost
from app.db.base import _utc_now_iso
from app.prompts.registry import registry
from app.repositories.agent_run import AgentRunRepository
from app.research.context import ResearchContext
from app.research.memory import seed_agents_md
from app.research.progress import ProgressBus
from app.research.service import RUBRIC_STEP_NODE, research_thread_id
from app.streaming.research_events import ResearchDone, ResearchError, derive_events

logger = logging.getLogger(__name__)

_DEFAULT_INSTRUCTION = "Research this trip in depth and produce a proposal."
_RESEARCH_NS_KIND = "research"
_PROPOSAL_KEY = "/proposal.json"


def _grader_rubric() -> str:
    """The grader rubric text supplied via ``state['rubric']``; an empty sentinel
    (grading disabled) if the prompt is unavailable, so a missing prompt never
    aborts a run."""
    try:
        return registry.get("trip_research_grader")
    except Exception:
        logger.warning("[research] grader rubric unavailable; grading disabled")
        return ""


def _build_input(
    ctx: ResearchContext,
    instruction: str | None,
) -> dict:
    """The fresh-turn graph input (design §4); ``instruction`` is already PII-redacted
    by the caller (design §8). The message names the traveller's language: the model
    never sees ``state['language']``, which only the tools read."""
    language = LANGUAGE_NAMES[normalize(ctx.language)]
    departing = f"Departing from: {ctx.origin}\n" if ctx.origin else ""
    content = (
        f"{instruction or _DEFAULT_INSTRUCTION}\n\n{departing}Language: {language}"
    )
    return {
        "messages": [HumanMessage(content=content)],
        "rubric": _grader_rubric(),
        "trip_id": ctx.trip_id,
        "user_id": ctx.user_id,
        "preferences": "",
        "language": ctx.language,
    }


def _research_namespace(ctx: ResearchContext) -> tuple[str, ...]:
    return ("users", ctx.user_id, _RESEARCH_NS_KIND, ctx.trip_id)


def _dossier_files(store: object, ctx: ResearchContext) -> list[str]:
    try:
        items = store.search(_research_namespace(ctx))
        return sorted(item.key for item in items)
    except Exception:
        return []


def _proposal_ready(store: object, ctx: ResearchContext) -> bool:
    try:
        return store.get(_research_namespace(ctx), _PROPOSAL_KEY) is not None
    except Exception:
        return False


def _mark_resumed(
    steps: list[dict],
    resumed_from: str,
) -> list[dict]:
    """Stamp ``resumed_from`` onto the run's first step ``meta`` (design §4); a run
    with no recorded steps gets a synthetic marker step so the id is never lost."""
    if not steps:
        return [
            {
                "seq": 0,
                "kind": "node",
                "node": "research",
                "status": "ok",
                "meta": {"resumed_from": resumed_from},
            }
        ]
    first = dict(steps[0])
    first["meta"] = {**(first.get("meta") or {}), "resumed_from": resumed_from}
    out = list(steps)
    out[0] = first
    return out


def _error_step(
    steps: list[dict],
    error_type: str,
) -> dict:
    """A terminal ``node`` step recording ``error_type`` — the run row has no
    error column, so a failure is only durable as a step."""
    return {
        "seq": len(steps),
        "kind": "node",
        "node": "research",
        "status": "error",
        "error_type": error_type,
    }


def _rubric_step(
    steps: list[dict],
    rubric_status: str,
) -> dict:
    """A terminal step carrying the grader's verdict. ``status`` stays ``ok``: the run
    itself succeeded (the dossier exists); whether it *passed* is the verdict."""
    return {
        "seq": len(steps),
        "kind": "node",
        "node": RUBRIC_STEP_NODE,
        "status": "ok",
        "meta": {"rubric_status": rubric_status},
    }


async def _read_rubric_status(
    agent: CompiledStateGraph,
    config: dict,
) -> str | None:
    """``RubricMiddleware``'s terminal verdict for this turn, from the checkpoint. It
    never alters the reply on a rejected dossier, so this is the only place the
    runner can learn that the grader gave up (``max_iterations_reached``)."""
    try:
        state = await agent.aget_state(config)
    except Exception:  # noqa: BLE001 — a missing verdict must not fail a finished run
        logger.warning("[research] rubric status read failed", exc_info=True)
        return None
    value = (state.values or {}).get("_rubric_status")
    return value if isinstance(value, str) else None


def _finalize(
    *,
    run_id: str,
    ctx: ResearchContext,
    store: object,
    bus: ProgressBus,
    metrics: TurnMetricsHandler,
    session_factory: sessionmaker[Session],
    status: str,
    error_type: str | None,
    started: float,
    resumed_from: str | None,
    rubric_status: str | None = None,
) -> None:
    """Write the terminal run row + steps on the isolated factory and publish the
    terminal bus event. Every sub-step is best-effort so finalisation never raises."""
    try:
        metrics.close(started)
        metrics.close_if_open()
        metrics.cost_usd = estimate_cost(metrics.snapshot()["by_model"])
    except Exception:
        logger.warning("[research] metrics close failed run=%s", run_id, exc_info=True)

    snapshot = metrics.snapshot()
    repo = AgentRunRepository(session_factory)
    try:
        repo.finish(
            run_id,
            status=status,
            current_flow=_RESEARCH_NS_KIND,
            finished_at=_utc_now_iso(),
            metrics=snapshot,
        )
    except Exception:
        logger.exception("[research] finish failed run=%s", run_id)

    try:
        steps = enrich_steps(metrics.steps(), snapshot)
        if error_type is not None:
            steps = [*steps, _error_step(steps, error_type)]
        if resumed_from is not None:
            steps = _mark_resumed(steps, resumed_from)
        if rubric_status is not None:
            steps = [*steps, _rubric_step(steps, rubric_status)]
        repo.add_steps(run_id, steps)
    except Exception:
        logger.exception("[research] add_steps failed run=%s", run_id)

    try:
        if status == "completed":
            bus.publish(
                run_id,
                ResearchDone(
                    status=status,
                    files=_dossier_files(store, ctx),
                    proposal_ready=_proposal_ready(store, ctx),
                ),
            )
        else:
            bus.publish(
                run_id,
                ResearchError(
                    code=error_type or "error", message="research run failed"
                ),
            )
    except Exception:
        logger.warning(
            "[research] terminal publish failed run=%s", run_id, exc_info=True
        )

    # Release the channel now the run is terminal: without this every finished run
    # leaks its ring buffer for the life of the process, and ``bus.has(run_id)``
    # stays True forever, so the SSE snapshot fallback becomes unreachable for any
    # run this process ever saw. Ordering is safe with no grace period: the terminal
    # event was already enqueued on every subscriber above, and ``close`` only
    # appends a sentinel after it — an ``asyncio.Queue`` is FIFO and both puts run
    # synchronously here with no ``await`` between, so a mid-stream subscriber always
    # dequeues the terminal event before the sentinel. A late subscriber (arriving
    # after close) instead takes the DB-snapshot branch, which the finished run row
    # already backs. ``close`` is synchronous, so this never delays the return.
    try:
        bus.close(run_id)
    except Exception:
        logger.warning("[research] bus close failed run=%s", run_id, exc_info=True)


async def run_trip_research(
    *,
    run_id: str,
    ctx: ResearchContext,
    instruction: str | None,
    agent: CompiledStateGraph,
    bus: ProgressBus,
    session_factory: sessionmaker[Session],
    resumed_from: str | None = None,
) -> None:
    """Drive one research turn to a terminal run row. Never raises (BackgroundTask).

    A fresh turn passes a built input; a resume passes ``None`` so the agent
    continues its checkpointed thread (design §4). The whole stream is bounded by
    ``settings.research_timeout_s``; on timeout or any failure the run finalises as
    ``failed`` with ``error_type`` recorded on a terminal step.
    """
    settings = get_settings()
    store = getattr(agent, "store", None)

    try:
        seed_agents_md(store, ctx.user_id)
    except Exception:
        logger.warning("[research] seed_agents_md failed run=%s", run_id, exc_info=True)

    metrics = TurnMetricsHandler()
    started = time.monotonic()
    stream_input = None if resumed_from is not None else _build_input(ctx, instruction)
    config = {
        "configurable": {"thread_id": research_thread_id(ctx.user_id, ctx.trip_id)},
        "callbacks": [metrics],
    }

    status = "completed"
    error_type: str | None = None
    rubric_status: str | None = None
    try:
        async with asyncio.timeout(settings.research_timeout_s):
            # v3 astream_events returns a coroutine resolving to the event stream.
            stream = await agent.astream_events(
                stream_input,
                config,
                version="v3",
                context=ctx,
            )
            async for event in stream:
                for research_event in derive_events(event):
                    bus.publish(run_id, research_event)
        rubric_status = await _read_rubric_status(agent, config)
    except Exception as exc:
        # Includes asyncio.timeout's TimeoutError. Nothing may escape a BackgroundTask.
        status = "failed"
        error_type = type(exc).__name__
        # exc_info: the class name alone ("BadRequestError") cannot be debugged —
        # the provider's message is the whole diagnosis.
        logger.warning(
            "[research] run=%s failed: %s",
            run_id,
            error_type,
            exc_info=True,
        )
    finally:
        _finalize(
            run_id=run_id,
            ctx=ctx,
            store=store,
            bus=bus,
            metrics=metrics,
            session_factory=session_factory,
            status=status,
            error_type=error_type,
            started=started,
            resumed_from=resumed_from,
            rubric_status=rubric_status,
        )
