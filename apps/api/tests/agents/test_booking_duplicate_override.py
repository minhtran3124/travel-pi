"""End-to-end duplicate-override refusal through the real graph (gh-200, task 2.2).

Drives the whole graph (plan interrupt → approve → booking → reflection) with a
pre-existing OWNER booking for the seeded flight, and pins the two halves of the
same-tool override guard through the real ``ToolNode`` error path — never a
hand-built ``ToolMessage``:

- **Same turn (SC-8):** the first scripted ``book_flight`` trips the duplicate
  check and returns an *error* ``ToolMessage`` whose content carries the
  id-bearing ``[possible-duplicate:<existing-id>]`` marker. The judge REVISEs,
  the revise-run ``book_flight(allow_duplicate=True)`` is refused (the traveller
  has not confirmed since the warning) and returns a second error carrying
  ``OVERRIDE_REFUSED_HINT`` — still exactly one row.
- **New turn (SC-9):** continuing on the same thread, a fresh traveller message
  ("yes, book it again") means the override is now honoured, so the scripted
  ``book_flight(allow_duplicate=True)`` succeeds and a second row is created.

The ``HumanMessage`` is created id-less on purpose: ``add_messages`` assigns a
stable id the checkpointer keeps across interrupt/resume, so the turn-scoped
idempotency key is identical on both booking runs of a turn.

``book_flight`` is trip-scoped (``trip_id`` via ``InjectedState``): the turn runs
with a real OWNER-owned trip and ``trip_id`` in state so the trip guard does not
block it, and the duplicate/override behaviour is what each case asserts.
"""

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
    """Point DATABASE_URL at a fresh seeded temp SQLite DB so the real booking
    tools run in-graph (they resolve their session from the setting, not a
    request). Kept local so this module is self-contained and free of a
    cross-package fixture import."""
    url = f"sqlite:///{tmp_path / 'booking_dup_override.db'}"
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


def _seed_trip_and_flight(url: str) -> tuple[str, str, str, str]:
    """Seed a trip, resolve the first HAN→SGN flight, and pre-book it for OWNER.

    Returns ``(trip_id, flight_number, flight_id, existing_booking_id)``. The
    pre-seeded booking uses ``passengers=1`` so the duplicate check (match key =
    flight row + passengers) fires against the scripted call, whose ``passengers``
    default is also 1.
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

    ``trip_id`` / ``user_id`` are injected from graph state, so they are *not* in
    the model-visible args — keeping the args (and thus the idempotency key)
    identical across booking runs of the turn. ``allow_duplicate`` is added only
    when set, so the default call's args match the pre-seeded booking exactly."""
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


# ---------------------------------------------------------------------------
# SC-8: same turn — warning, then a REVISE override is refused; one row.
# ---------------------------------------------------------------------------


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

    # First call: duplicate check trips; the id-bearing marker names the existing
    # booking. The error ToolMessage does NOT end the turn (the commit guard
    # requires status != "error"), so the judge runs and REVISEs.
    assert booked[0].content.startswith("Tool call failed:")
    m = DUPLICATE_WARNING_MARKER_RE.search(booked[0].content)
    assert m is not None
    assert m.group(1) == existing_id

    # Second call (allow_duplicate=True) is refused: the traveller has not
    # confirmed since the warning in this same turn.
    assert OVERRIDE_REFUSED_HINT in booked[1].content

    # Judge ran exactly once (REVISE); DEFAULT_MAX_REVISIONS = 1 ends the turn
    # after the second booking run, before the scripted "OK" is reached.
    assert fast._cursor == 1
    assert main._cursor == 4

    assert _rows(agent_db) == 1


# ---------------------------------------------------------------------------
# SC-9: a new traveller turn confirms — the override is honoured; two rows.
# ---------------------------------------------------------------------------


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

    # A NEW traveller turn on the SAME thread confirms — now the override is
    # honoured because the traveller has spoken since the warning.
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

    # The committed booking ends the second turn before the judge runs, so fast
    # is still at the single REVISE consumed on the first turn.
    assert fast._cursor == 1
