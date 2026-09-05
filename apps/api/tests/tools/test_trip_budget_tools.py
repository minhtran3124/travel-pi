"""``estimate_trip_budget`` + ``set_trip_budget`` tools (specs/agent-budget-trip-context Task 1.1).

Both take ``user_id`` / ``trip_id`` via ``InjectedState`` (auto-derived schema,
no ``args_schema=``), so the model-facing ``tool_call_schema`` must exclude
them and a real ``ToolNode`` run must still inject them.
"""

import json
from datetime import date

import pytest
from app.agents.state import TravelAgentState
from app.db.engine import get_session_factory
from app.schemas.trip import TripCreate
from app.services.trip_service import TripService
from langchain_core.messages import AIMessage
from langchain_core.tools import ToolException
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

USER = "test-user-1"


def _tool_node_graph(tool):
    """Compile a minimal one-node graph so ToolNode gets a real LangGraph
    runtime (CONFIG_KEY_RUNTIME) to resolve InjectedState from — a bare
    ``ToolNode(...).invoke(state_dict)`` has no runtime and raises
    "Missing required config key" before injection ever runs.
    """
    graph = StateGraph(TravelAgentState)
    graph.add_node("tools", ToolNode([tool]))
    graph.set_entry_point("tools")
    graph.add_edge("tools", END)
    return graph.compile()


def _create_trip(agent_db, **kwargs) -> str:
    with get_session_factory(agent_db)() as s:
        trip = TripService(s, USER).create_trip(TripCreate(**kwargs))
        s.commit()
        return trip.id


@pytest.fixture
def dated_trip_id(agent_db):
    return _create_trip(
        agent_db,
        title="Da Nang long weekend",
        city="Da Nang",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 4),
        travelers=2,
    )


# ---------------------------------------------------------------- SC-2: set


def test_set_trip_budget_persists_caps_and_replaces(trip_id):
    from app.tools.trip_tools import get_trip_budget, set_trip_budget

    out = set_trip_budget.invoke(
        {
            "trip_id": trip_id,
            "user_id": USER,
            "flights": 300.0,
            "hotels": 450.0,
            "activities": 120.0,
            "buffer": 80.0,
        }
    )
    assert out["categories"]["flights"]["cap"] == 300.0
    assert out["categories"]["buffer"]["cap"] == 80.0

    shown = get_trip_budget.invoke({"trip_id": trip_id, "user_id": USER})
    assert shown["categories"]["flights"]["cap"] == 300.0
    assert shown["categories"]["hotels"]["cap"] == 450.0
    assert shown["categories"]["activities"]["cap"] == 120.0
    assert shown["categories"]["buffer"]["cap"] == 80.0

    # Replace semantics: omitting a category uncaps it.
    set_trip_budget.invoke(
        {"trip_id": trip_id, "user_id": USER, "flights": 300.0, "hotels": 450.0}
    )
    shown = get_trip_budget.invoke({"trip_id": trip_id, "user_id": USER})
    assert shown["categories"]["flights"]["cap"] == 300.0
    assert shown["categories"]["hotels"]["cap"] == 450.0
    assert shown["categories"]["activities"]["cap"] is None
    assert shown["categories"]["buffer"]["cap"] is None


def test_set_trip_budget_no_caps_raises_and_leaves_existing_untouched(trip_id):
    from app.tools.trip_tools import get_trip_budget, set_trip_budget

    set_trip_budget.invoke(
        {"trip_id": trip_id, "user_id": USER, "flights": 300.0, "hotels": 450.0}
    )
    with pytest.raises(ToolException, match="No cap supplied"):
        set_trip_budget.invoke({"trip_id": trip_id, "user_id": USER})
    shown = get_trip_budget.invoke({"trip_id": trip_id, "user_id": USER})
    assert shown["categories"]["flights"]["cap"] == 300.0
    assert shown["categories"]["hotels"]["cap"] == 450.0


def test_set_trip_budget_not_found_raises(agent_db):
    from app.tools.trip_tools import set_trip_budget

    with pytest.raises(ToolException):
        set_trip_budget.invoke({"trip_id": "missing", "user_id": USER, "flights": 1.0})


def test_set_trip_budget_injected_via_tool_node(trip_id):
    """Prove user_id/trip_id resolve via InjectedState through a real ToolNode."""
    from app.tools.trip_tools import set_trip_budget

    compiled = _tool_node_graph(set_trip_budget)
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "set_trip_budget",
                "args": {"flights": 200.0, "buffer": 50.0},
                "id": "call-1",
            }
        ],
    )
    result = compiled.invoke(
        {"messages": [ai_msg], "trip_id": trip_id, "user_id": USER}
    )
    tool_msgs = [m for m in result["messages"] if m.__class__.__name__ == "ToolMessage"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].status != "error"
    payload = json.loads(tool_msgs[0].content)
    assert payload["categories"]["flights"]["cap"] == 200.0
    assert payload["categories"]["buffer"]["cap"] == 50.0
    assert payload["categories"]["hotels"]["cap"] is None


# ------------------------------------------------------------ SC-3: derive


def test_estimate_trip_budget_derives_nights_and_travelers(dated_trip_id):
    from app.tools.trip_tools import estimate_trip_budget

    out = estimate_trip_budget.invoke(
        {"trip_id": dated_trip_id, "user_id": USER, "hotel_price_per_night_usd": 100.0}
    )
    assert out["nights"] == 3
    assert out["travelers"] == 2
    assert out["city"] == "Da Nang"
    caps = out["suggested_caps"]
    # Only the hotel price was given: flights stay uncapped (key absent), never 0.
    assert set(caps) == {"hotels", "activities", "buffer"}
    assert caps["hotels"] == out["breakdown"]["accommodation"]
    assert caps["activities"] == out["breakdown"]["activities"]
    assert sum(caps.values()) == pytest.approx(out["total_estimate"])


def test_estimate_trip_budget_no_prices_omits_flights_and_hotels(dated_trip_id):
    from app.tools.trip_tools import estimate_trip_budget

    out = estimate_trip_budget.invoke({"trip_id": dated_trip_id, "user_id": USER})
    caps = out["suggested_caps"]
    assert "flights" not in caps
    assert "hotels" not in caps
    assert set(caps) == {"activities", "buffer"}
    assert sum(caps.values()) == pytest.approx(out["total_estimate"])


def test_estimate_trip_budget_known_prices_cap_all_four(dated_trip_id):
    from app.tools.trip_tools import estimate_trip_budget

    out = estimate_trip_budget.invoke(
        {
            "trip_id": dated_trip_id,
            "user_id": USER,
            "flight_total_usd": 300.0,
            "hotel_price_per_night_usd": 80.0,
        }
    )
    caps = out["suggested_caps"]
    assert set(caps) == {"flights", "hotels", "activities", "buffer"}
    assert caps["flights"] == 300.0
    assert caps["hotels"] == 80.0 * out["nights"]
    assert sum(caps.values()) == pytest.approx(out["total_estimate"])


def test_estimate_trip_budget_explicit_args_override_derived(dated_trip_id):
    from app.tools.trip_tools import estimate_trip_budget

    out = estimate_trip_budget.invoke(
        {"trip_id": dated_trip_id, "user_id": USER, "nights": 5, "travelers": 1}
    )
    assert out["nights"] == 5
    assert out["travelers"] == 1


# ---------------------------------------------------------- SC-4: no dates


def test_estimate_trip_budget_no_dates_returns_guidance(trip_id):
    from app.tools.trip_tools import estimate_trip_budget

    out = estimate_trip_budget.invoke({"trip_id": trip_id, "user_id": USER})
    assert out["error"] == "trip_dates_unknown"
    assert "hint" in out
    assert "suggested_caps" not in out


def test_estimate_trip_budget_only_start_date_returns_guidance(agent_db):
    from app.tools.trip_tools import estimate_trip_budget

    tid = _create_trip(
        agent_db, title="Open-ended", city="Hanoi", start_date=date(2026, 10, 1)
    )
    out = estimate_trip_budget.invoke({"trip_id": tid, "user_id": USER})
    assert out["error"] == "trip_dates_unknown"
    assert "hint" in out


def test_estimate_trip_budget_no_dates_with_explicit_nights(trip_id):
    from app.tools.trip_tools import estimate_trip_budget

    out = estimate_trip_budget.invoke(
        {"trip_id": trip_id, "user_id": USER, "nights": 2}
    )
    assert out["nights"] == 2
    assert out["travelers"] == 1  # trip default
    assert sum(out["suggested_caps"].values()) == pytest.approx(out["total_estimate"])


def test_estimate_trip_budget_zero_nights_raises(trip_id):
    from app.tools.trip_tools import estimate_trip_budget

    with pytest.raises(ToolException):
        estimate_trip_budget.invoke({"trip_id": trip_id, "user_id": USER, "nights": 0})


# ----------------------------------------------------------- guards/schema


def test_no_active_trip_and_missing_user():
    from app.tools.trip_tools import estimate_trip_budget, set_trip_budget

    for t in (estimate_trip_budget, set_trip_budget):
        assert t.invoke({"user_id": USER})["error"] == "no_active_trip"
        with pytest.raises(ToolException):
            t.invoke({"trip_id": "x"})


def test_model_facing_schema_excludes_injected_and_describes_fields():
    from app.tools.trip_tools import estimate_trip_budget, set_trip_budget

    for t in (estimate_trip_budget, set_trip_budget):
        props = t.tool_call_schema.model_json_schema()["properties"]
        assert "user_id" not in props, t.name
        assert "trip_id" not in props, t.name
        for name, field in t.tool_call_schema.model_fields.items():
            assert field.description, f"{t.name}.{name}"
    assert set(set_trip_budget.tool_call_schema.model_fields) == {
        "flights",
        "hotels",
        "activities",
        "buffer",
    }
    assert "meal_style" in estimate_trip_budget.tool_call_schema.model_fields
