"""Persistence wrapper for the agent SSE stream.

Wraps ``stream_agent_events`` to accumulate the assistant's reply from ``token``
events and write it to the DB **before** the terminal ``done`` event reaches
the client (specs/user-feedback-v1 DESIGN §4.3). Uses an **isolated**
sessionmaker-backed session (not the request-scoped Depends session, which may
be torn down before or during streaming) — see rules/guidelines.md Data Access.

The caller passes a ``session_factory`` so the same DB engine used for the
request-scoped session is reused. This lets tests override ``get_session`` once
and have the propagation flow through automatically (instead of reading
``get_settings()`` here and hitting the real DB in tests).

On ``reset`` events (reflection revision) the accumulator is cleared so only
the *final* answer is persisted, mirroring the FE's reset semantics in
``streaming/mapper.py``.

``done`` therefore means "the answer is durable": it carries the persisted
row's ``assistant_message_id`` and the ``agent_run_id`` that produced it, and
is never yielded when there is no row (empty reply or insert failure) — a
terminal ``error`` is emitted instead.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from sqlalchemy.orm import Session, sessionmaker

from app.core.streaming import TypedSSEEvent
from app.repositories.conversation import ConversationRepository
from app.streaming import events

logger = logging.getLogger(__name__)


async def persist_assistant_turn(
    events_iter: AsyncIterator[TypedSSEEvent],
    *,
    conversation_id: str,
    session_factory: sessionmaker[Session],
    run_id: str,
    message_id: str,
) -> AsyncIterator[TypedSSEEvent]:
    """Pass every SSE event through while persisting the assistant reply on ``done``.

    Tokens (since the last ``reset``) are accumulated. When the upstream ``done``
    arrives the text is inserted as an ``assistant`` message under the
    pre-minted ``message_id`` with ``agent_run_id=run_id`` via ``session_factory``
    (an isolated session — not the request-scoped one) **before** ``done`` is
    yielded, and both ids are injected into the ``done`` payload. An empty reply
    or a failed insert emits a terminal ``error`` and suppresses ``done``.
    ``interrupt`` / ``error`` pass through untouched (``record_agent_run`` owns
    the run status). The mapper emits ``done`` after ``interrupt`` too; that
    turn has no reply row (DESIGN §4.2: interrupt ⇒ ``assistant_message_id``
    null, not rateable), so it passes through with a null message id.

    :param events_iter: The upstream SSE event stream to pass through.
    :param conversation_id: The conversation the persisted turn belongs to.
    :param session_factory: Isolated sessionmaker used to write the message.
    :param run_id: The ``agent_runs`` id the router started for this turn.
    :param message_id: The router-minted id the assistant row is stored under.
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
        elif event.event == "done" and interrupted:
            event = _with_identity(event, message_id=None, run_id=run_id)
        elif event.event == "done":
            text = "".join(accumulated)
            if not text:
                logger.error(
                    "[persist_assistant_turn] empty reply on done for conv=%s run=%s",
                    conversation_id,
                    run_id,
                )
                yield events.error(
                    code="empty_reply", message="The assistant produced no reply."
                )
                continue
            try:
                ConversationRepository(session_factory).append_message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=text,
                    message_id=message_id,
                    agent_run_id=run_id,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "[persist_assistant_turn] failed to persist assistant message "
                    "for conv=%s run=%s: %s",
                    conversation_id,
                    run_id,
                    exc,
                )
                yield events.error(
                    code="persistence_failed",
                    message="The reply could not be saved.",
                )
                continue
            logger.debug(
                "[persist_assistant_turn] persisted assistant message %s for conv=%s",
                message_id,
                conversation_id,
            )
            event = _with_identity(event, message_id=message_id, run_id=run_id)
        yield event


def _with_identity(
    done: TypedSSEEvent, *, message_id: str | None, run_id: str
) -> TypedSSEEvent:
    """Return ``done`` with ``assistant_message_id`` / ``agent_run_id`` injected."""
    payload = json.loads(done.data)
    payload["assistant_message_id"] = message_id
    payload["agent_run_id"] = run_id
    return TypedSSEEvent(event="done", data=json.dumps(payload, separators=(",", ":")))
