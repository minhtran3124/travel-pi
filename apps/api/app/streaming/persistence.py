"""Persistence wrapper for the agent SSE stream.

Wraps ``stream_agent_events`` to accumulate the assistant's reply from ``token``
events and write it to the DB once the stream finishes. Uses an **isolated**
sessionmaker-backed session (not the request-scoped Depends session, which may
be torn down before or during streaming) — see rules/guidelines.md Data Access.

The caller passes a ``session_factory`` so the same DB engine used for the
request-scoped session is reused. This lets tests override ``get_session`` once
and have the propagation flow through automatically (instead of reading
``get_settings()`` here and hitting the real DB in tests).

On ``reset`` events (a later sub-agent superseded the answer) the accumulator is cleared so only
the *final* answer is persisted, mirroring the FE's reset semantics in
``streaming/mapper.py``.
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
) -> AsyncIterator[TypedSSEEvent]:
    """Pass every SSE event through unchanged while persisting the assistant reply.

    After the inner iterator is exhausted the accumulated assistant text (from all
    ``token`` events since the last ``reset``) is written to the DB as an
    ``assistant`` message via ``session_factory`` (an isolated session — not the
    request-scoped one).  An empty accumulated text is silently skipped (Rule 2).

    :param events_iter: The upstream SSE event stream to pass through.
    :param conversation_id: The conversation the persisted turn belongs to.
    :param session_factory: Isolated sessionmaker used to write the message.
    """
    accumulated: list[str] = []

    async for event in events_iter:
        yield event
        if event.event == "token":
            try:
                content = json.loads(event.data).get("content", "")
            except (ValueError, KeyError):
                content = ""
            if content:
                accumulated.append(content)
        elif event.event == "reset":
            accumulated.clear()

    text = "".join(accumulated)
    if not text:
        return

    try:
        repo = ConversationRepository(session_factory)
        repo.append_message(
            conversation_id=conversation_id, role="assistant", content=text
        )
        logger.debug(
            "[persist_assistant_turn] persisted assistant message for conv=%s",
            conversation_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[persist_assistant_turn] failed to persist assistant message for conv=%s: %s",
            conversation_id,
            exc,
        )
