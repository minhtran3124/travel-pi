"""``persist_assistant_turn`` — persist-before-``done`` (specs/user-feedback-v1 §4.3).

Drives the wrapper with a scripted async SSE iterator against a real
``ConversationRepository`` on a tmp SQLite factory and asserts, *inside the
consuming loop*, that the assistant row already exists when ``done`` is yielded,
that ``done`` carries the pre-minted ``assistant_message_id`` + ``agent_run_id``,
and that ``done`` is never withheld: an empty reply, a failed insert or an
interrupted turn still deliver ``done`` with ``assistant_message_id: null``
(DESIGN §4.3 as amended — "no effect on the chatbot"). A terminal upstream
``error`` that follows streamed text (the mapper's fallback reply on a graph
failure) persists that text before the ``error`` is yielded, as does
interrupted draft text.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.models import Message
from app.repositories.conversation import ConversationRepository
from app.streaming import events
from app.streaming.persistence import persist_assistant_turn

RUN_ID = "run-1"
MSG_ID = "msg-1"


@pytest.fixture
def factory(tmp_path):
    url = f"sqlite:///{tmp_path / 'persist.db'}"
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    return get_session_factory(url)


async def _script(items):
    for ev in items:
        yield ev


def _row(factory, message_id=MSG_ID) -> Message | None:
    with factory() as s:
        return s.get(Message, message_id)


def _drain(factory, items, *, on_event=None):
    """Consume the wrapper; ``on_event`` runs per yielded event (for in-loop asserts)."""

    async def run():
        out = []
        async for ev in persist_assistant_turn(
            _script(items),
            conversation_id="c1",
            session_factory=factory,
            run_id=RUN_ID,
            message_id=MSG_ID,
        ):
            if on_event is not None:
                on_event(ev)
            out.append((ev.event, json.loads(ev.data)))
        return out

    return asyncio.run(run())


def _done():
    return events.done(conversation_id="c1", current_flow="planner", suggestions=[])


def test_done_carries_ids_and_row_exists_when_done_is_yielded(factory):
    seen_at_done: dict = {}

    def on_event(ev):
        if ev.event == "done":
            # The row must be committed BEFORE the client can see `done`.
            seen_at_done["row"] = _row(factory)

    out = _drain(
        factory,
        [events.start("c1"), events.token("Hel"), events.token("lo"), _done()],
        on_event=on_event,
    )

    assert [e for e, _ in out] == ["start", "token", "token", "done"]
    done = out[-1][1]
    assert done["assistant_message_id"] == MSG_ID
    assert done["agent_run_id"] == RUN_ID
    assert done["current_flow"] == "planner"  # rest of the payload untouched
    row = seen_at_done["row"]
    assert row is not None
    assert row.role == "assistant"
    assert row.content == "Hello"
    assert row.agent_run_id == RUN_ID
    assert row.conversation_id == "c1"


def test_reset_persists_only_the_final_answer(factory):
    out = _drain(
        factory,
        [events.token("draft"), events.reset(), events.token("final"), _done()],
    )
    assert out[-1][0] == "done"
    assert _row(factory).content == "final"


def test_empty_reply_yields_done_with_null_id_and_no_row(factory):
    """A tool/panel-only turn has no text: ``done`` passes exactly as before this
    feature (never an ``empty_reply`` error), with a null message id."""
    out = _drain(factory, [events.start("c1"), _done()])
    assert [e for e, _ in out] == ["start", "done"]
    done = out[-1][1]
    assert done["assistant_message_id"] is None
    assert done["agent_run_id"] == RUN_ID
    assert done["current_flow"] == "planner"  # rest of the payload untouched
    assert _row(factory) is None


def test_insert_failure_still_yields_done_with_null_id(factory, monkeypatch, caplog):
    """A failed insert must not turn the reply the traveller already saw into an
    error: log it, yield ``done`` with a null id (not rateable)."""

    def _boom(self, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(ConversationRepository, "append_message", _boom)
    with caplog.at_level("ERROR", logger="app.streaming.persistence"):
        out = _drain(factory, [events.token("Hello"), _done()])
    assert [e for e, _ in out] == ["token", "done"]
    assert out[-1][1]["assistant_message_id"] is None
    assert out[-1][1]["agent_run_id"] == RUN_ID
    assert _row(factory) is None
    assert any("db down" in r.getMessage() for r in caplog.records)


def test_interrupt_then_done_saves_draft_and_yields_null_message_id(factory):
    """The mapper emits ``done`` after ``interrupt``; the draft text is saved
    (as before this feature) but the turn is not rateable, so ``done`` carries
    a null ``assistant_message_id`` (DESIGN §4.2)."""
    seen_at_done: dict = {}

    def on_event(ev):
        if ev.event == "done":
            seen_at_done["row"] = _row(factory)

    interrupt = events.interrupt(conversation_id="c1", payload={"plan": "x"})
    out = _drain(
        factory, [events.token("partial"), interrupt, _done()], on_event=on_event
    )
    assert [e for e, _ in out] == ["token", "interrupt", "done"]
    assert out[-1][1]["assistant_message_id"] is None
    assert out[-1][1]["agent_run_id"] == RUN_ID
    row = seen_at_done["row"]
    assert row is not None
    assert row.content == "partial"
    assert row.agent_run_id == RUN_ID


def test_interrupt_then_done_without_text_writes_no_row(factory):
    interrupt = events.interrupt(conversation_id="c1", payload={"plan": "x"})
    out = _drain(factory, [events.start("c1"), interrupt, _done()])
    assert [e for e, _ in out] == ["start", "interrupt", "done"]
    assert out[-1][1]["assistant_message_id"] is None
    assert _row(factory) is None


def test_interrupt_terminal_passes_through_without_a_row(factory):
    interrupt = events.interrupt(conversation_id="c1", payload={"plan": "x"})
    out = _drain(factory, [events.token("partial"), interrupt])
    assert [e for e, _ in out] == ["token", "interrupt"]
    assert _row(factory) is None


def test_error_with_text_persists_reply_before_error_is_yielded(factory):
    """Graph failure: the mapper streams a fallback ``token`` then ``error`` and
    never ``done``. The text is saved under the pre-minted id (history parity
    with the REST fallback reply) and the ``error`` payload is untouched."""
    seen_at_error: dict = {}

    def on_event(ev):
        if ev.event == "error":
            seen_at_error["row"] = _row(factory)

    error = events.error(code="internal", message="boom")
    out = _drain(
        factory,
        [events.token("Sorry, "), events.token("try again"), error],
        on_event=on_event,
    )
    assert [e for e, _ in out] == ["token", "token", "error"]
    assert out[-1][1] == {"code": "internal", "message": "boom"}  # no ids injected
    row = seen_at_error["row"]
    assert row is not None
    assert row.role == "assistant"
    assert row.content == "Sorry, try again"
    assert row.agent_run_id == RUN_ID
    assert row.conversation_id == "c1"


def test_error_without_text_writes_no_row(factory):
    error = events.error(code="internal", message="boom")
    out = _drain(factory, [events.start("c1"), error])
    assert [e for e, _ in out] == ["start", "error"]
    assert out[-1][1] == {"code": "internal", "message": "boom"}
    assert _row(factory) is None


def test_error_persist_failure_is_swallowed_and_error_still_passes(
    factory, monkeypatch
):
    def _boom(self, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(ConversationRepository, "append_message", _boom)
    error = events.error(code="internal", message="boom")
    out = _drain(factory, [events.token("partial"), error])
    assert [e for e, _ in out] == ["token", "error"]
    assert out[-1][1] == {"code": "internal", "message": "boom"}
    assert _row(factory) is None


def test_interrupt_then_error_saves_draft_text(factory):
    """Draft text of an interrupted turn that then errors is kept for history
    (not rateable — the run ends interrupted/failed); ``error`` is untouched."""
    interrupt = events.interrupt(conversation_id="c1", payload={"plan": "x"})
    error = events.error(code="internal", message="boom")
    out = _drain(factory, [events.token("partial"), interrupt, error])
    assert [e for e, _ in out] == ["token", "interrupt", "error"]
    assert out[-1][1] == {"code": "internal", "message": "boom"}
    row = _row(factory)
    assert row is not None
    assert row.content == "partial"
    assert row.agent_run_id == RUN_ID


def test_cancelled_error_writes_no_row_even_with_partial_text(factory):
    """A client disconnect (error code ``cancelled``) is not a reply the
    traveller saw; the partial text is dropped (DESIGN §4.3)."""
    error = events.error(code="cancelled", message="Stream cancelled")
    out = _drain(factory, [events.token("partial"), error])
    assert [e for e, _ in out] == ["token", "error"]
    assert _row(factory) is None
