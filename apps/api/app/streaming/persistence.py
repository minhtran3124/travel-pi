"""Persistence wrapper for the agent SSE stream.

Accumulates the assistant reply from ``token`` events and writes it to the DB
before the terminal ``done`` reaches the client. Uses an isolated
sessionmaker-backed session (not the request-scoped one, which may be torn down
during streaming); the caller passes ``session_factory`` so tests can override
``get_session`` once. ``reset`` clears the accumulator so only the final answer
is persisted. A ``done`` with a saved row carries its ``assistant_message_id`` /
``agent_run_id``, else null; a terminal ``error`` (or ``interrupt``) with
accumulated text persists it too, but that turn is never rateable.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from sqlalchemy.orm import Session, sessionmaker

from app.core.streaming import TypedSSEEvent
from app.repositories.conversation import ConversationRepository

logger = logging.getLogger(__name__)


async def persist_assistant_turn(
    events_iter: AsyncIterator[TypedSSEEvent],
    *,
    conversation_id: str,
    session_factory: sessionmaker[Session],
    run_id: str,
    message_id: str,
) -> AsyncIterator[TypedSSEEvent]:
    """Pass every SSE event through while persisting the assistant reply.

    Accumulated tokens (since the last ``reset``) are written under the pre-minted
    ``message_id`` before ``done`` is yielded, and both ids are injected into it.
    An empty reply, failed insert, or interrupted turn yields ``done`` with
    ``assistant_message_id: null``. A terminal ``error`` with accumulated text
    persists it (history parity with the REST fallback); an ``error`` with no
    text, or code ``cancelled`` (client disconnect), writes nothing.
    """
    accumulated: list[str] = []
    interrupted = False

    async for event in events_iter:
        if event.event == "token":
            try:
                content = json.loads(event.data).get("content", "")
            except (ValueError, KeyError):
                content = ""
            if content:
                accumulated.append(content)
        elif event.event == "reset":
            accumulated.clear()
        elif event.event == "interrupt":
            interrupted = True
        elif event.event == "error":
            # A client disconnect surfaces as error{code: cancelled}; the
            # traveller never saw a reply, so no row.
            try:
                code = json.loads(event.data).get("code")
            except (ValueError, AttributeError):
                code = None
            if code != "cancelled":
                # Persist the fallback/draft reply before the client sees the
                # failure; record_agent_run marks the run failed/interrupted, so
                # the row is history-only, never rateable.
                _save_best_effort(
                    session_factory,
                    conversation_id=conversation_id,
                    text="".join(accumulated),
                    message_id=message_id,
                    run_id=run_id,
                    context="error",
                )
        elif event.event == "done":
            text = "".join(accumulated)
            if interrupted:
                # Draft text of an interrupted turn is kept for history but the
                # turn is not rateable.
                _save_best_effort(
                    session_factory,
                    conversation_id=conversation_id,
                    text=text,
                    message_id=message_id,
                    run_id=run_id,
                    context="done after interrupt",
                )
                event = _with_identity(event, message_id=None, run_id=run_id)
            elif not text:
                event = _with_identity(event, message_id=None, run_id=run_id)
            else:
                saved = _save_best_effort(
                    session_factory,
                    conversation_id=conversation_id,
                    text=text,
                    message_id=message_id,
                    run_id=run_id,
                    context="done",
                )
                event = _with_identity(
                    event, message_id=message_id if saved else None, run_id=run_id
                )
        yield event


def _save_best_effort(
    session_factory: sessionmaker[Session],
    *,
    conversation_id: str,
    text: str,
    message_id: str,
    run_id: str,
    context: str,
) -> bool:
    """Insert *text* as the assistant row; log and swallow any failure.

    Returns ``True`` when a row was written, ``False`` for empty text or a failure.
    """
    if not text:
        return False
    try:
        _append_assistant(
            session_factory,
            conversation_id=conversation_id,
            text=text,
            message_id=message_id,
            run_id=run_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[persist_assistant_turn] failed to persist assistant message on %s "
            "for conv=%s run=%s: %s",
            context,
            conversation_id,
            run_id,
            exc,
        )
        return False
    return True


def _append_assistant(
    session_factory: sessionmaker[Session],
    *,
    conversation_id: str,
    text: str,
    message_id: str,
    run_id: str,
) -> None:
    """Insert the assistant row under the pre-minted id, linked to its run."""
    ConversationRepository(session_factory).append_message(
        conversation_id=conversation_id,
        role="assistant",
        content=text,
        message_id=message_id,
        agent_run_id=run_id,
    )
    logger.debug(
        "[persist_assistant_turn] persisted assistant message %s for conv=%s",
        message_id,
        conversation_id,
    )


def _with_identity(
    done: TypedSSEEvent, *, message_id: str | None, run_id: str
) -> TypedSSEEvent:
    """Return ``done`` with ``assistant_message_id`` / ``agent_run_id`` injected."""
    payload = json.loads(done.data)
    payload["assistant_message_id"] = message_id
    payload["agent_run_id"] = run_id
    return TypedSSEEvent(event="done", data=json.dumps(payload, separators=(",", ":")))
