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

``done`` therefore carries the persisted row's ``assistant_message_id`` and
the ``agent_run_id`` that produced it when a rateable row exists, and
``assistant_message_id: null`` otherwise (empty reply, interrupted turn, or a
failed insert). ``done`` itself is never withheld or replaced: the stream's
terminal contract is exactly what it was before this feature.

A terminal ``error`` that arrives *with* accumulated text (the mapper streams a
fallback ``token`` and then ``error`` when the graph fails — see
``streaming/mapper.py``) is also persisted under the pre-minted id, so REST
and SSE history stay in parity (the chat path saves its fallback reply the
same way). That run ends ``failed`` via ``record_agent_run``, so the row is
not rateable; the ``error`` payload itself is passed through untouched. The
same applies after an ``interrupt``: draft text is saved (as it was before this
feature) but the turn is never rateable.
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

    Tokens (since the last ``reset``) are accumulated. When the upstream ``done``
    arrives the text is inserted as an ``assistant`` message under the
    pre-minted ``message_id`` with ``agent_run_id=run_id`` via ``session_factory``
    (an isolated session — not the request-scoped one) **before** ``done`` is
    yielded, and both ids are injected into the ``done`` payload. ``done`` is
    always yielded: an empty reply writes no row, a failed insert is logged, and
    an interrupted turn saves its draft text (not rateable) — each of those
    yields ``done`` with ``assistant_message_id: null`` (DESIGN §4.2/§4.3).
    ``interrupt`` / ``error`` pass through untouched (``record_agent_run`` owns
    the run status). A terminal ``error`` with non-empty accumulated text (the
    mapper's fallback reply) persists that text under ``message_id`` **before**
    the ``error`` is yielded — history parity with the REST fallback — and a
    failure to do so is logged and swallowed (the client already has an
    error). An ``error`` with no text, or with code ``cancelled`` (client
    disconnect — the traveller never saw the reply), writes nothing.

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
        elif event.event == "error":
            # A client disconnect surfaces as error{code: cancelled}; the
            # traveller never saw a reply, so no row (DESIGN §4.3).
            try:
                code = json.loads(event.data).get("code")
            except (ValueError, AttributeError):
                code = None
            if code != "cancelled":
                # Persist the (fallback / draft) reply before the client sees
                # the failure; the run is marked `failed` or `interrupted` by
                # record_agent_run, so the row is history-only, never rateable.
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
                # Draft text of an interrupted turn is kept for history (as it
                # was before this feature) but the turn is not rateable.
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
                # No reply text: no row, `done` passes as it always did.
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

    :return: ``True`` when a row was written, ``False`` for empty text or a
        failed insert (the caller then reports a null ``assistant_message_id``).
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
