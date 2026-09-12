"""End-to-end booking turn does not revise (gh-193, task 2.2, SC-5).

Drives the whole graph (plan interrupt → approve → booking → reflection) with a
judge scripted to say REVISE, and pins the two halves of the fix:

- **Part B (the guard, case 1):** a turn that committed a booking is terminal.
  Reflection ends it *before* calling the judge, the booking sub-agent runs once,
  exactly one booking row exists, and no revise note is persisted.
- **Part A (idempotency, case 2):** with the guard disabled the judge REVISEs,
  the booking sub-agent runs a second time, but the second ``book_flight`` call
  replays the first booking via the turn-scoped key — still one row, and the two
  ``book_flight`` ToolMessages carry the same booking id.

The ``HumanMessage`` is created id-less on purpose: LangGraph's ``add_messages``
assigns it a stable id when it enters state, and the checkpointer keeps that id
across the interrupt/resume, so the idempotency key is identical on both booking
runs of the same turn — that stability is part of what case 2 proves.

``book_flight`` is trip-scoped (``trip_id`` via ``InjectedState``): the booking
sub-agent's trip guard blocks it with an *error* ToolMessage and ends the turn
when no trip is active. The turn therefore runs with a real OWNER-owned trip and
``trip_id`` in state, and every ``book_flight`` ToolMessage is asserted
``status == "success"`` so a guard block cannot masquerade as a passing case 1.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from app.agents.constants import REFLECTION_REVISE_NOTE
from app.agents.graph import build_graph
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from app.core.config import get_settings
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.services.booking_service import BookingService
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command
from pydantic import PrivateAttr

OWNER = "u_booking_turn"


@pytest.fixture
def agent_db(tmp_path, monkeypatch):
    """Point DATABASE_URL at a fresh seeded temp SQLite DB so the real booking
    tools run in-graph (they resolve their session from the setting, not a
    request). Mirrors ``tests/agents/test_plan_everything.py``; kept local so this
    module is self-contained and free of a cross-package fixture import."""
    url = f"sqlite:///{tmp_path / 'booking_turn.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    seed_all(get_session_factory(url))
    yield url
    get_settings.cache_clear()


def _drive(graph, *args, **kwargs):
    """Run the graph the way production does — asynchronously (a specialist binds
    async-only tools, so a sync ``invoke`` cannot execute its worker node)."""
    return asyncio.run(graph.ainvoke(*args, **kwargs))


def _build(main: FakeLLM, fast: FakeLLM):
    return build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )


def _invoke(graph, msg: str, *, trip_id: str, thread_id: str):
    # HumanMessage is intentionally id-less: add_messages assigns a stable id
    # that the checkpointer keeps across interrupt/resume (the turn boundary the
    # idempotency key is built from).
    return _drive(
        graph,
        {
            "messages": [HumanMessage(content=msg)],
            "user_id": OWNER,
            "trip_id": trip_id,
        },
        {"configurable": {"thread_id": thread_id}},
    )


def _seed_trip_and_flight(url: str) -> tuple[str, str]:
    from app.schemas.trip import TripCreate
    from app.services.flight_service import FlightService
    from app.services.trip_service import TripService

    with get_session_factory(url)() as s:
        flight_number = (
            FlightService(s).search_flights("HAN", "SGN", "2027-03-15")[0].flight_number
        )
        trip = TripService(s, OWNER).create_trip(
            TripCreate(title="HAN to SGN", city="Hanoi")
        )
        s.commit()
        return trip.id, flight_number


def _book_flight_call(flight_number: str, call_id: str) -> AIMessage:
    """A scripted assistant turn calling book_flight with the seeded flight.

    ``trip_id`` / ``user_id`` are injected from graph state, so they are *not* in
    the model-visible args — keeping the args (and thus the idempotency key)
    identical across both booking runs of the turn."""
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "book_flight",
                "args": {
                    "flight_number": flight_number,
                    "origin": "HAN",
                    "destination": "SGN",
                    "departure_date": "2027-03-15",
                    "passenger_name": "Test User",
                    "passenger_email": "test@example.com",
                    "passenger_phone": "+1 555 000 0000",
                    "confirm": True,
                },
                "id": call_id,
            }
        ],
    )


def _rows(url: str) -> int:
    with get_session_factory(url)() as s:
        return len(BookingService(s).list_all(user_id=OWNER))


def _book_flight_tool_messages(messages: list) -> list[ToolMessage]:
    return [
        m for m in messages if isinstance(m, ToolMessage) and m.name == "book_flight"
    ]


def _booking_id(tool_message: ToolMessage) -> str:
    # book_flight returns ``dump(result)`` (a dict); ToolNode serialises a
    # non-string tool return into ToolMessage.content as JSON.
    return json.loads(tool_message.content)["id"]


# ---------------------------------------------------------------------------
# Case 1 (guard on): reflection ends before the judge; booking runs once.
# ---------------------------------------------------------------------------


def test_booking_turn_with_guard_never_revises(agent_db):
    trip_id, flight_number = _seed_trip_and_flight(agent_db)
    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent="booking")],
        responses=[
            _book_flight_call(flight_number, "call-1"),
            "Booked!",
            _book_flight_call(flight_number, "call-2"),
            "Booked again",
        ],
    )
    fast = FakeLLM(responses=["REVISE", "OK"])
    graph = _build(main, fast)
    thread_id = "t-booking-guard-on"

    first = _invoke(graph, "book HAN to SGN", trip_id=trip_id, thread_id=thread_id)
    assert first.get("__interrupt__"), "booking must still pause at plan_node"

    out = _drive(
        graph,
        Command(resume={"approved": True}),
        {"configurable": {"thread_id": thread_id}},
    )

    assert not out.get("__interrupt__")

    # The booking actually ran (guard block would be status="error").
    booked = _book_flight_tool_messages(out["messages"])
    assert booked, "book_flight must have run this turn"
    assert all(m.status == "success" for m in booked)

    # The guard ended the turn before the judge ran.
    assert fast._cursor == 0
    # The booking assistant ran exactly once (one tool call + one answer).
    assert main._cursor == 2

    assert _rows(agent_db) == 1

    ai_contents = [m.content for m in out["messages"] if isinstance(m, AIMessage)]
    assert ai_contents[-1] == "Booked!"
    assert all("Booked again" not in (m.content or "") for m in out["messages"])

    # No revise note was persisted, and no revision was taken.
    assert not any(
        isinstance(m, SystemMessage) and REFLECTION_REVISE_NOTE in m.content
        for m in out["messages"]
    )
    assert out.get("revisions", 0) == 0


# ---------------------------------------------------------------------------
# Case 2 (guard off): REVISE re-runs booking; the second call replays the key.
# ---------------------------------------------------------------------------


def test_booking_turn_without_guard_revises_but_replays_booking(agent_db, monkeypatch):
    # Disable the reflection guard so REVISE re-runs the booking sub-agent — the
    # literal issue this whole change fixes end to end (part A).
    monkeypatch.setattr("app.agents.nodes.BOOKING_WRITE_TOOLS", frozenset())

    trip_id, flight_number = _seed_trip_and_flight(agent_db)
    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent="booking")],
        responses=[
            _book_flight_call(flight_number, "call-1"),
            "Booked!",
            _book_flight_call(flight_number, "call-2"),
            "Booked again",
        ],
    )
    fast = FakeLLM(responses=["REVISE", "OK"])
    graph = _build(main, fast)
    thread_id = "t-booking-guard-off"

    first = _invoke(graph, "book HAN to SGN", trip_id=trip_id, thread_id=thread_id)
    assert first.get("__interrupt__"), "booking must still pause at plan_node"

    out = _drive(
        graph,
        Command(resume={"approved": True}),
        {"configurable": {"thread_id": thread_id}},
    )

    assert not out.get("__interrupt__")

    # The judge ran once and said REVISE, so the booking sub-agent ran a second
    # time; DEFAULT_MAX_REVISIONS is 1, so the second reflection short-circuits at
    # revisions=1 and ends the turn BEFORE a second judge call (the scripted "OK"
    # is never reached — mirrors tests/agents/test_multi_intent_routing.py).
    assert fast._cursor == 1
    assert main._cursor == 4

    booked = _book_flight_tool_messages(out["messages"])
    assert len(booked) == 2
    assert all(m.status == "success" for m in booked)

    # Both calls resolved to the SAME booking — the second replayed via the
    # turn-scoped idempotency key — so there is still exactly one row.
    assert _booking_id(booked[0]) == _booking_id(booked[1])
    assert _rows(agent_db) == 1


# ---------------------------------------------------------------------------
# Retry (guard on): a transient LLM fault AFTER the write is retried, books once.
# ---------------------------------------------------------------------------


class _RetryOnceFakeLLM(FakeLLM):
    """``FakeLLM`` that raises a retryable fault once, on a chosen response slot.

    ``fail_at`` is the ``responses`` cursor position whose FIRST delivery raises a
    ``ConnectionError`` -- a fault ``app.agents.retry._is_retryable_llm`` accepts --
    *without* consuming the slot, so the assistant node's ``LLM_RETRY`` re-runs it
    and the retried call returns that same scripted response normally. ``_calls``
    counts every delivery attempt (the failed one included), so a test can assert
    it is exactly one higher than the number of responses actually consumed
    (``_cursor``) -- i.e. that one retry happened.
    """

    fail_at: int = 0
    _failed: bool = PrivateAttr(default=False)
    _calls: int = PrivateAttr(default=0)

    def _build_next(self) -> AIMessage:
        self._calls += 1
        if self._cursor == self.fail_at and not self._failed:
            self._failed = True
            raise ConnectionError("simulated transient LLM failure")
        return super()._build_next()


def test_booking_turn_llm_retry_after_write_books_once(agent_db):
    # Fail the narration call (cursor 1) -- the assistant turn that runs AFTER the
    # successful book_flight tool call, so the write has already happened when the
    # retry re-runs the assistant. LLM_RETRY on the booking assistant node must
    # re-run it and finish the turn with a single booking, not a second write.
    trip_id, flight_number = _seed_trip_and_flight(agent_db)
    main = _RetryOnceFakeLLM(
        fail_at=1,
        structured_responses=[SupervisorIntent(target_agent="booking")],
        responses=[
            _book_flight_call(flight_number, "call-1"),
            "Booked!",
        ],
    )
    fast = FakeLLM(responses=["REVISE", "OK"])
    graph = _build(main, fast)
    thread_id = "t-booking-llm-retry"

    first = _invoke(graph, "book HAN to SGN", trip_id=trip_id, thread_id=thread_id)
    assert first.get("__interrupt__"), "booking must still pause at plan_node"

    out = _drive(
        graph,
        Command(resume={"approved": True}),
        {"configurable": {"thread_id": thread_id}},
    )

    # The turn completed -- the retried narration surfaced, no interrupt.
    assert not out.get("__interrupt__")
    ai_contents = [m.content for m in out["messages"] if isinstance(m, AIMessage)]
    assert ai_contents[-1] == "Booked!"

    # The retry actually fired: exactly one delivery attempt raised, so the call
    # counter is one higher than the number of scripted responses consumed.
    assert main._failed
    assert main._calls == main._cursor + 1

    # The write ran once and succeeded -- exactly one booking row, one success
    # ToolMessage (a guard block would be status="error"), and no revision.
    booked = _book_flight_tool_messages(out["messages"])
    assert len(booked) == 1
    assert booked[0].status == "success"
    assert _rows(agent_db) == 1
    assert out.get("revisions", 0) == 0
