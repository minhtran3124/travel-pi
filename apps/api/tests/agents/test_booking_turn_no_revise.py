"""End-to-end booking turn does not revise even when the judge says REVISE."""

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
    """Fresh seeded temp SQLite DB so in-graph booking tools resolve a session from the setting."""
    url = f"sqlite:///{tmp_path / 'booking_turn.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    seed_all(get_session_factory(url))
    yield url
    get_settings.cache_clear()


def _drive(graph, *args, **kwargs):
    """Run the graph asynchronously; a specialist binds async-only tools, so sync invoke cannot execute its worker node."""
    return asyncio.run(graph.ainvoke(*args, **kwargs))


def _build(main: FakeLLM, fast: FakeLLM):
    return build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )


def _invoke(graph, msg: str, *, trip_id: str, thread_id: str):
    # HumanMessage is id-less on purpose: add_messages assigns a stable id the
    # checkpointer keeps across interrupt/resume, the turn boundary the
    # idempotency key is built from.
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
    """Scripted book_flight call; trip_id/user_id inject from state, so args (and the idempotency key) match across both booking runs."""
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
    # book_flight returns a dict; ToolNode serialises a non-string return into ToolMessage.content as JSON.
    return json.loads(tool_message.content)["id"]


# Case 1 (guard on): reflection ends before the judge; booking runs once.
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


# Case 2 (guard off): REVISE re-runs booking; the second call replays the key.
def test_booking_turn_without_guard_revises_but_replays_booking(agent_db, monkeypatch):
    # Disable the reflection guard so REVISE re-runs the booking sub-agent.
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

    # Judge said REVISE so the sub-agent ran twice; DEFAULT_MAX_REVISIONS is 1,
    # so the second reflection short-circuits at revisions=1 and ends the turn
    # before a second judge call (the scripted "OK" is never reached).
    assert fast._cursor == 1
    assert main._cursor == 4

    booked = _book_flight_tool_messages(out["messages"])
    assert len(booked) == 2
    assert all(m.status == "success" for m in booked)

    # Both calls resolved to the SAME booking — the second replayed via the
    # turn-scoped idempotency key — so there is still exactly one row.
    assert _booking_id(booked[0]) == _booking_id(booked[1])
    assert _rows(agent_db) == 1


# Retry (guard on): a transient LLM fault after the write is retried, books once.
class _RetryOnceFakeLLM(FakeLLM):
    """FakeLLM whose fail_at slot raises a retryable ConnectionError once without consuming the slot; _calls counts every attempt so a test can prove one retry happened."""

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
    # Fail the narration call (cursor 1), which runs after the successful write,
    # so LLM_RETRY re-running the assistant must not produce a second write.
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
