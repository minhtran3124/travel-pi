"""Framework-agnostic post-turn memory extraction runner.

Lifts the body of ``app.agents.nodes.make_extract_memory_node`` into a plain
function so it can be invoked outside a LangGraph node (e.g. from a
background task). Best-effort: any error is swallowed so a failed extraction
never breaks the caller.
"""

from __future__ import annotations

import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langgraph.store.base import BaseStore

from app.memory.extractor import extract_memories
from app.memory.store import upsert_episode, upsert_instruction, upsert_preference

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
    """
    if not allow_memory_write:
        logger.info("[agent] extract_memory (skipped — allow_memory_write=False)")
        return None

    if not user_id or store is None:
        logger.info("[agent] extract_memory (skipped — no user_id or store)")
        return None

    try:
        extracted = extract_memories(messages, llm)
        for pref in extracted.preferences:
            upsert_preference(store, user_id, pref["key"], {"text": pref["text"]})
        for instr in extracted.instructions:
            upsert_instruction(store, user_id, instr["key"], {"text": instr["text"]})
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
            "[agent] extract_memory preferences=%d instructions=%d episodes=%d",
            len(extracted.preferences),
            len(extracted.instructions),
            len(extracted.episodes),
        )
    except Exception:
        logger.exception("[agent] extract_memory: write failed")
    return None


def run_memory_extraction_from_stream(
    *,
    sink: dict,
    allow_memory_write: bool,
    store: BaseStore | None,
    llm: BaseChatModel,
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
    )
    return None
