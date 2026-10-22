"""End-to-end duplicate-override refusal driven through the real graph and ToolNode error path."""

from __future__ import annotations

import asyncio

import pytest
from app.agents.graph import build_graph
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from app.core.config import get_settings
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.exceptions import DUPLICATE_WARNING_MARKER_RE
from app.schemas.flight import FlightBookingRequest
from app.services.booking_service import BookingService
from app.tools._idempotency import OVERRIDE_REFUSED_HINT
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

OWNER = "u_booking_dup_override"


@pytest.fixture
def agent_db(tmp_path, monkeypatch):
    """Point DATABASE_URL at a fresh seeded temp DB so the real in-graph booking tools resolve a session from the setting."""
    url = f"sqlite:///{tmp_path / 'booking_dup_override.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    seed_all(get_session_factory(url))
    yield url
    get_settings.cache_clear()


def _drive(graph, *args, **kwargs):
    """Run the graph asynchronously: a specialist binds async-only tools a sync invoke cannot execute."""
    return asyncio.run(graph.ainvoke(*args, **kwargs))


def _build(main: FakeLLM, fast: FakeLLM):
    return build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )


def _invoke(graph, msg: str, *, trip_id: str, thread_id: str):
    # Id-less HumanMessage: add_messages assigns a stable id the checkpointer keeps
    # across interrupt/resume — the turn boundary the idempotency key is built from.
    return _drive(
        graph,
        {
            "messages": [HumanMessage(content=msg)],
            "user_id": OWNER,
            "trip_id": trip_id,
        },
        {"configurable": {"thread_id": thread_id}},
    )


def _seed_trip_and_flight(url: str) -> tuple[str, str, str, str]:
    """Seed a trip, resolve the first HAN→SGN flight, and pre-book it for OWNER.

    passengers=1 matches the scripted call's default so the duplicate check (key =
    flight row + passengers) fires.
    """
    from app.schemas.trip import TripCreate
    from app.services.flight_service import FlightService
    from app.services.trip_service import TripService

    with get_session_factory(url)() as s:
        flight = FlightService(s).search_flights("HAN", "SGN", "2027-03-15")[0]
        trip = TripService(s, OWNER).create_trip(
            TripCreate(title="HAN to SGN", city="Hanoi")
        )
        existing = BookingService(s).book_flight(
            FlightBookingRequest(
                flight_id=flight.id,
                passengers=1,
                passenger_name="Test User",
                passenger_email="test@example.com",
                passenger_phone="+1 555 000 0000",
            ),
            user_id=OWNER,
        )
        s.commit()
        return trip.id, flight.flight_number, flight.id, existing.id


def _book_flight_call(
    flight_number: str, call_id: str, *, allow_duplicate: bool = False
) -> AIMessage:
    """A scripted assistant turn calling book_flight with the seeded flight.

    trip_id/user_id are injected from state (not in model-visible args), keeping the
    idempotency key identical across booking runs of the turn.
    """
    args = {
        "flight_number": flight_number,
        "origin": "HAN",
        "destination": "SGN",
        "departure_date": "2027-03-15",
        "passenger_name": "Test User",
        "passenger_email": "test@example.com",
        "passenger_phone": "+1 555 000 0000",
        "confirm": True,
    }
    if allow_duplicate:
        args["allow_duplicate"] = True
    return AIMessage(
        content="",
        tool_calls=[{"name": "book_flight", "args": args, "id": call_id}],
    )


def _rows(url: str) -> int:
    with get_session_factory(url)() as s:
        return len(BookingService(s).list_all(user_id=OWNER))


def _book_flight_tool_messages(messages: list) -> list[ToolMessage]:
    return [
        m for m in messages if isinstance(m, ToolMessage) and m.name == "book_flight"
    ]


def test_booking_duplicate_override_same_turn_refused(agent_db):
    trip_id, flight_number, _flight_id, existing_id = _seed_trip_and_flight(agent_db)
    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent="booking")],
        responses=[
            _book_flight_call(flight_number, "call-1"),
            "You already hold this booking — book again?",
            _book_flight_call(flight_number, "call-2", allow_duplicate=True),
            "Waiting for your confirmation",
        ],
    )
    fast = FakeLLM(responses=["REVISE", "OK"])
    graph = _build(main, fast)
    thread_id = "t-dup-override-same-turn"

    first = _invoke(graph, "book HAN to SGN", trip_id=trip_id, thread_id=thread_id)
    assert first.get("__interrupt__"), "booking must still pause at plan_node"

    out = _drive(
        graph,
        Command(resume={"approved": True}),
        {"configurable": {"thread_id": thread_id}},
    )
    assert not out.get("__interrupt__")

    booked = _book_flight_tool_messages(out["messages"])
    assert len(booked) == 2
    assert all(m.status == "error" for m in booked)

    # The error ToolMessage does not end the turn (commit guard requires
    # status != "error"), so the judge runs and REVISEs.
    assert booked[0].content.startswith("Tool call failed:")
    m = DUPLICATE_WARNING_MARKER_RE.search(booked[0].content)
    assert m is not None
    assert m.group(1) == existing_id

    # Override refused: the traveller has not confirmed since the warning this turn.
    assert OVERRIDE_REFUSED_HINT in booked[1].content

    # DEFAULT_MAX_REVISIONS = 1 ends the turn before the scripted "OK" is reached.
    assert fast._cursor == 1
    assert main._cursor == 4

    assert _rows(agent_db) == 1


def test_booking_duplicate_override_new_turn_books(agent_db):
    trip_id, flight_number, _flight_id, _existing_id = _seed_trip_and_flight(agent_db)
    # FakeLLM.responses cycles by `_cursor % len`, so the second turn's call needs
    # its own slots — 4 entries would replay call-1 on the new turn.
    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent="booking")],
        responses=[
            _book_flight_call(flight_number, "call-1"),
            "You already hold this booking — book again?",
            _book_flight_call(flight_number, "call-2", allow_duplicate=True),
            "Waiting for your confirmation",
            _book_flight_call(flight_number, "call-3", allow_duplicate=True),
            "Booked again",
        ],
    )
    fast = FakeLLM(responses=["REVISE", "OK"])
    graph = _build(main, fast)
    thread_id = "t-dup-override-new-turn"

    first = _invoke(graph, "book HAN to SGN", trip_id=trip_id, thread_id=thread_id)
    assert first.get("__interrupt__"), "booking must still pause at plan_node"
    out = _drive(
        graph,
        Command(resume={"approved": True}),
        {"configurable": {"thread_id": thread_id}},
    )
    assert not out.get("__interrupt__")
    assert _rows(agent_db) == 1

    # New turn on the same thread: the override is honoured now the traveller confirmed.
    second = _invoke(graph, "yes, book it again", trip_id=trip_id, thread_id=thread_id)
    if second.get("__interrupt__"):
        second = _drive(
            graph,
            Command(resume={"approved": True}),
            {"configurable": {"thread_id": thread_id}},
        )
    assert not second.get("__interrupt__")

    booked = _book_flight_tool_messages(second["messages"])
    assert booked[-1].status == "success"
    assert _rows(agent_db) == 2

    # The committed booking ends the second turn before the judge runs.
    assert fast._cursor == 1
