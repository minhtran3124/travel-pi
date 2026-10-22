"""``list_trips`` tool (specs/gh-166-list-trips-tool Task 1.1).

The tool answers "how many trips do I have" — the one question the injected
``trip_id`` (a single open trip) cannot answer. It takes ``user_id`` /
``trip_id`` via ``InjectedState`` with no ``args_schema=``, so the model-facing
schema must expose neither, and a real ``ToolNode`` run must still inject both.

Unlike every sibling trip tool, an absent ``trip_id`` is a normal state here:
the tool returns an ordinary result with every ``is_active`` false rather than
the ``no_active_trip`` guidance value.
"""

import json
from datetime import date

import pytest
from app.agents.state import TravelAgentState
from app.db.engine import get_session_factory
from app.enums import TripItemKind
from app.schemas.trip import TripCreate, TripItemCreate
from app.services.trip_service import TripService
from langchain_core.messages import AIMessage
from langchain_core.tools import ToolException
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

USER = "test-user-1"
OTHER_USER = "test-user-2"


def _tool_node_graph(tool):
    """Compile a minimal one-node graph so ToolNode gets a real LangGraph
    runtime to resolve InjectedState from (a bare ``ToolNode(...).invoke(...)``
    raises "Missing required config key" before injection runs).
    """
    graph = StateGraph(TravelAgentState)
    graph.add_node("tools", ToolNode([tool]))
    graph.set_entry_point("tools")
    graph.add_edge("tools", END)
    return graph.compile()


def _create_trip(agent_db, user: str, created_at: str, **kwargs) -> str:
    """Create a trip owned by ``user`` and stamp an explicit ``created_at``.

    The order contract is ``created_at DESC``. Rows created in one test run can
    otherwise share a timestamp to the stored precision, which makes the
    newest-first assertion a coin flip — so each fixture row pins its own value.
    """
    from app.db import models

    factory = get_session_factory(agent_db)
    with factory() as s:
        trip = TripService(s, user).create_trip(TripCreate(**kwargs))
        s.commit()
        trip_id = trip.id
    with factory() as s:
        row = s.get(models.Trip, trip_id)
        row.created_at = created_at
        s.commit()
    return trip_id


@pytest.fixture
def two_trips(agent_db):
    """Two trips for USER: the Da Nang one is newer than the Tokyo one."""
    older = _create_trip(
        agent_db,
        USER,
        "2026-01-01T00:00:00+00:00",
        title="Tokyo trip",
        city="Tokyo",
        travelers=1,
    )
    newer = _create_trip(
        agent_db,
        USER,
        "2026-02-01T00:00:00+00:00",
        title="Da Nang long weekend",
        city="Da Nang",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 4),
        travelers=2,
        items=[
            TripItemCreate(day=1, kind=TripItemKind.PLACE, title="Marble Mountains"),
            TripItemCreate(day=2, kind=TripItemKind.PLACE, title="My Khe Beach"),
        ],
    )
    return {"older": older, "newer": newer}


# ------------------------------------------------------- SC-1: count + order


def test_list_trips_counts_and_orders_newest_first(two_trips):
    from app.tools.trip_tools import list_trips

    out = list_trips.invoke({"user_id": USER, "trip_id": two_trips["newer"]})

    assert out["count"] == 2
    assert [t["title"] for t in out["trips"]] == [
        "Da Nang long weekend",
        "Tokyo trip",
    ]


def test_list_trips_marks_only_the_injected_trip_as_active(two_trips):
    from app.tools.trip_tools import list_trips

    out = list_trips.invoke({"user_id": USER, "trip_id": two_trips["older"]})

    active = [t["title"] for t in out["trips"] if t["is_active"]]
    assert active == ["Tokyo trip"]


def test_list_trips_without_active_trip_returns_normal_result(two_trips):
    """No open trip is a valid state for this question: a normal result, never
    the ``no_active_trip`` guidance value the sibling trip tools return."""
    from app.tools.trip_tools import list_trips

    out = list_trips.invoke({"user_id": USER, "trip_id": None})

    assert "error" not in out
    assert out["count"] == 2
    assert [t["is_active"] for t in out["trips"]] == [False, False]


def test_list_trips_with_no_trips_returns_empty(agent_db):
    from app.tools.trip_tools import list_trips

    assert list_trips.invoke({"user_id": USER, "trip_id": None}) == {
        "count": 0,
        "trips": [],
    }


def test_list_trips_injected_via_tool_node(two_trips):
    """user_id / trip_id resolve via InjectedState through a real ToolNode, and
    neither is model-facing."""
    from app.tools.trip_tools import list_trips

    assert set(list_trips.tool_call_schema.model_fields) == set()

    compiled = _tool_node_graph(list_trips)
    ai_msg = AIMessage(
        content="",
        tool_calls=[{"name": "list_trips", "args": {}, "id": "call-1"}],
    )
    result = compiled.invoke(
        {"messages": [ai_msg], "trip_id": two_trips["newer"], "user_id": USER}
    )
    tool_msgs = [m for m in result["messages"] if m.__class__.__name__ == "ToolMessage"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].status != "error"
    payload = json.loads(tool_msgs[0].content)
    assert payload["count"] == 2


# ----------------------------------------------------------- SC-4: ownership


def test_list_trips_never_returns_another_owners_trips(two_trips, agent_db):
    from app.tools.trip_tools import list_trips

    _create_trip(
        agent_db,
        OTHER_USER,
        "2026-03-01T00:00:00+00:00",
        title="Someone else's Hanoi trip",
        city="Hanoi",
    )

    out = list_trips.invoke({"user_id": USER, "trip_id": None})

    assert out["count"] == 2
    assert "Someone else's Hanoi trip" not in [t["title"] for t in out["trips"]]


def test_list_trips_without_owner_raises(agent_db):
    from app.tools.trip_tools import list_trips

    with pytest.raises(ToolException, match="user_id"):
        list_trips.invoke({"user_id": None, "trip_id": None})


# ---------------------------------------------------------- SC-2: projection


def test_list_trips_projection_omits_id_and_counts_items(two_trips):
    from app.tools.trip_tools import list_trips

    out = list_trips.invoke({"user_id": USER, "trip_id": two_trips["newer"]})

    newest = out["trips"][0]
    assert set(newest) == {
        "title",
        "city",
        "start_date",
        "end_date",
        "travelers",
        "items",
        "is_active",
    }
    assert "id" not in newest
    assert newest["items"] == 2
    assert isinstance(newest["items"], int)
    assert out["trips"][1]["items"] == 0


# ------------------------------------------------------ SC-7: serialisability


def test_list_trips_result_is_json_serializable(two_trips):
    from app.tools.trip_tools import list_trips

    out = list_trips.invoke({"user_id": USER, "trip_id": two_trips["newer"]})

    encoded = json.dumps(out)
    assert "2026-10-01" in encoded
    newest = out["trips"][0]
    assert newest["start_date"] == "2026-10-01"
    assert newest["end_date"] == "2026-10-04"
