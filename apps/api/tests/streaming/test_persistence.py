"""``persist_assistant_turn`` — persist-before-``done`` (specs/user-feedback-v1 §4.3).

Drives the wrapper with a scripted async SSE iterator against a real
``ConversationRepository`` on a tmp SQLite factory and asserts, *inside the
consuming loop*, that the assistant row already exists when ``done`` is yielded,
that ``done`` carries the pre-minted ``assistant_message_id`` + ``agent_run_id``,
and that an empty reply or a failed insert yields a terminal ``error`` instead.
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


def test_empty_reply_emits_error_and_no_done_and_no_row(factory):
    out = _drain(factory, [events.start("c1"), _done()])
    assert [e for e, _ in out] == ["start", "error"]
    assert out[-1][1]["code"] == "empty_reply"
    assert _row(factory) is None


def test_insert_failure_emits_error_and_no_done(factory, monkeypatch):
    def _boom(self, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(ConversationRepository, "append_message", _boom)
    out = _drain(factory, [events.token("Hello"), _done()])
    assert [e for e, _ in out] == ["token", "error"]
    assert out[-1][1]["code"] == "persistence_failed"
    assert "db down" not in out[-1][1]["message"]  # internals stay out of the wire
    assert _row(factory) is None


def test_interrupt_then_done_passes_through_with_null_message_id(factory):
    """The mapper emits ``done`` after ``interrupt``; that turn has no reply row
    (DESIGN §4.2), so ``done`` is kept — never turned into ``empty_reply``."""
    interrupt = events.interrupt(conversation_id="c1", payload={"plan": "x"})
    out = _drain(factory, [events.token("partial"), interrupt, _done()])
    assert [e for e, _ in out] == ["token", "interrupt", "done"]
    assert out[-1][1]["assistant_message_id"] is None
    assert out[-1][1]["agent_run_id"] == RUN_ID
    assert _row(factory) is None


def test_interrupt_and_error_pass_through_without_a_row(factory):
    interrupt = events.interrupt(conversation_id="c1", payload={"plan": "x"})
    out = _drain(factory, [events.token("partial"), interrupt])
    assert [e for e, _ in out] == ["token", "interrupt"]
    assert _row(factory) is None

    error = events.error(code="internal", message="boom")
    out = _drain(factory, [events.token("partial"), error])
    assert [e for e, _ in out] == ["token", "error"]
    assert out[-1][1] == {"code": "internal", "message": "boom"}
    assert _row(factory) is None
