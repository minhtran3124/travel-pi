"""Framework-agnostic post-turn memory extraction runner.

Lifts the body of ``app.agents.nodes.make_extract_memory_node`` into a plain
function so it can be invoked outside a LangGraph node (e.g. from a
background task). Best-effort: any error is swallowed so a failed extraction
never breaks the caller.
"""

from __future__ import annotations

import logging
import time

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langgraph.store.base import BaseStore
from sqlalchemy.orm import sessionmaker

from app.agents.metrics import TurnMetricsHandler
from app.memory.extractor import extract_memories
from app.memory.store import upsert_episode, upsert_instruction, upsert_preference
from app.repositories.agent_run import AgentRunRepository

logger = logging.getLogger(__name__)


def run_memory_extraction(
    *,
    messages: list[BaseMessage],
    user_id: str | None,
    trip_id: str | None,
    plan_approved: bool,
    allow_memory_write: bool,
    store: BaseStore | None,
    llm: BaseChatModel,
    run_id: str | None = None,
    session_factory: sessionmaker | None = None,
) -> None:
    """Extract preferences/instructions/episodes from *messages* and upsert them.

    Best-effort: any error during extraction or store writes is logged and
    swallowed, never raised.

    :param messages: Full conversation history to extract from.
    :param user_id: Owning user id; extraction is skipped if falsy.
    :param trip_id: Trip id used as an episode key fallback.
    :param plan_approved: When True, episodes are recorded with
        ``outcome="approved"`` regardless of the extractor's own outcome.
    :param allow_memory_write: Gate — extraction is skipped entirely if False.
    :param store: LangGraph store to write into; extraction is skipped if None.
    :param llm: Chat model used to run the extraction prompt.
    :param run_id: When set together with *session_factory*, the background LLM
        calls / tokens / wall-clock of this extraction are recorded onto the
        ``agent_runs`` row with this id (best-effort).
    :param session_factory: Session factory used to persist the background
        metrics; required alongside *run_id* for any DB write to happen.
    """
    if not allow_memory_write:
        logger.info("[agent] extract_memory (skipped — allow_memory_write=False)")
        return None

    if not user_id or store is None:
        logger.info("[agent] extract_memory (skipped — no user_id or store)")
        return None

    record_metrics = run_id is not None and session_factory is not None
    handler = TurnMetricsHandler() if record_metrics else None

    try:
        started = time.perf_counter()
        extracted = extract_memories(
            messages, llm, callbacks=[handler] if handler else None
        )
        for pref in extracted.preferences:
            upsert_preference(store, user_id, pref["key"], {"text": pref["text"]})
            logger.info(
                "[agent] extract_memory saved preference user=%s key=%s text=%r",
                user_id,
                pref["key"],
                pref["text"],
            )
        for instr in extracted.instructions:
            upsert_instruction(store, user_id, instr["key"], {"text": instr["text"]})
            logger.info(
                "[agent] extract_memory saved instruction user=%s key=%s text=%r",
                user_id,
                instr["key"],
                instr["text"],
            )
        # P2: persist episodes with rich metadata. A turn that passed the HITL
        # plan-approval gate (plan_approved=True) records outcome="approved";
        # otherwise the extractor's default ("proposed") stands.
        for ep in extracted.episodes:
            key = ep.get("key") or trip_id or "episode"
            outcome = "approved" if plan_approved else ep.get("outcome", "proposed")
            upsert_episode(
                store,
                user_id,
                key,
                {
                    "text": ep["text"],
                    "trip_id": trip_id,
                    "city": ep.get("city"),
                    "outcome": outcome,
                },
            )
            logger.info(
                "[agent] extract_memory saved episode user=%s key=%s city=%s "
                "outcome=%s text=%r",
                user_id,
                key,
                ep.get("city"),
                outcome,
                ep["text"],
            )
        logger.info(
            "[agent] extract_memory preferences=%d instructions=%d episodes=%d",
            len(extracted.preferences),
            len(extracted.instructions),
            len(extracted.episodes),
        )
    except Exception:
        logger.exception("[agent] extract_memory: write failed")

    # Record background metrics AFTER the memory writes, in an isolated try, so a
    # metrics-DB failure can never starve the primary preference/instruction/episode
    # upserts above (memory is the point of this task; metrics are secondary).
    if record_metrics:
        try:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            snap = handler.snapshot()
            AgentRunRepository(session_factory).add_background(
                run_id,
                llm_calls=snap["llm_calls"],
                tokens=snap["input_tokens"] + snap["output_tokens"],
                ms=elapsed_ms,
            )
        except Exception:
            logger.exception("[agent] extract_memory: background metrics record failed")
    return None


def run_memory_extraction_from_stream(
    *,
    sink: dict,
    allow_memory_write: bool,
    store: BaseStore | None,
    llm: BaseChatModel,
    run_id: str | None = None,
    session_factory: sessionmaker | None = None,
) -> None:
    """Adapt a streaming turn's post-drain ``sink`` into ``run_memory_extraction``.

    ``sink`` is populated by ``stream_agent_events`` after the SSE stream fully
    drains (see ``final_state_sink``); this adapter is the entry point a
    ``StreamingResponse`` background task calls, so extraction still runs off
    the reply path even though the final graph state is only known post-drain.
    No-op (best-effort) when the sink is empty (stream crashed before the
    post-drain fetch) or a plan-approval interrupt is pending.

    :param sink: The mutable dict populated by ``stream_agent_events`` with
        ``values`` (final graph state) and ``interrupt_pending``.
    :param allow_memory_write: Gate forwarded to ``run_memory_extraction``.
    :param store: LangGraph store to write into.
    :param llm: Chat model used to run the extraction prompt.
    :param run_id: Forwarded to ``run_memory_extraction`` for background metrics.
    :param session_factory: Forwarded to ``run_memory_extraction`` for background
        metric persistence.
    """
    if not sink or sink.get("interrupt_pending"):
        return None

    values = sink.get("values") or {}
    run_memory_extraction(
        messages=values.get("messages", []),
        user_id=values.get("user_id"),
        trip_id=values.get("trip_id"),
        plan_approved=values.get("plan_approved", False),
        allow_memory_write=allow_memory_write,
        store=store,
        llm=llm,
        run_id=run_id,
        session_factory=session_factory,
    )
    return None
