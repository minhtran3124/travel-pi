"""Where post-turn memory extraction runs: Arq worker or this process.

With ``REDIS_URL`` set the web process only enqueues (``app/worker.py`` runs the
job); otherwise extraction runs in a thread here, exactly as the old
``BackgroundTasks`` sync call did. Both are async so Starlette can schedule them
as background tasks.
"""

from __future__ import annotations

import asyncio
import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, messages_to_dict
from langgraph.store.base import BaseStore
from sqlalchemy.orm import sessionmaker

from app.core.queue import enqueue, queue_enabled
from app.memory.extraction_runner import run_memory_extraction

logger = logging.getLogger(__name__)


async def dispatch_memory_extraction(
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
    """Hand a finished turn to memory extraction.

    The queued job id is ``memory:<run_id>``, so a duplicate enqueue is a no-op. If
    the enqueue fails (Redis down) extraction runs in-process: it is best-effort
    either way and must never break the caller.
    """
    if queue_enabled() and run_id is not None:
        if not allow_memory_write or not user_id:
            logger.info("[agent] extract_memory (skipped — not writable or no user)")
            return
        try:
            await enqueue(
                "run_memory_extraction",
                run_id,
                messages_to_dict(messages),
                user_id,
                trip_id,
                plan_approved,
                job_id=f"memory:{run_id}",
            )
            return
        except Exception:
            logger.exception(
                "[agent] extract_memory enqueue failed run=%s; running in-process",
                run_id,
            )
    await asyncio.to_thread(
        run_memory_extraction,
        messages=messages,
        user_id=user_id,
        trip_id=trip_id,
        plan_approved=plan_approved,
        allow_memory_write=allow_memory_write,
        store=store,
        llm=llm,
        run_id=run_id,
        session_factory=session_factory,
    )


async def dispatch_memory_extraction_from_stream(
    *,
    sink: dict,
    allow_memory_write: bool,
    store: BaseStore | None,
    llm: BaseChatModel,
    run_id: str | None = None,
    session_factory: sessionmaker | None = None,
) -> None:
    """Streaming counterpart; same sink rules as ``run_memory_extraction_from_stream``
    (no-op on an empty sink or a pending plan-approval interrupt)."""
    if not sink or sink.get("interrupt_pending"):
        return
    values = sink.get("values") or {}
    await dispatch_memory_extraction(
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
