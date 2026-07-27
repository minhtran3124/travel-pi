"""Trip-tools schema + injection tests (specs/agent-trip-context Task 1.1).

``trip_id`` is injected via ``InjectedState`` (mirroring ``user_id`` in
``memory_tools.py``): an explicit ``args_schema=`` that omits it breaks
LangGraph's ToolNode injection, so these tools keep an auto-derived schema and
attach model-facing descriptions inline via ``Annotated[..., Field(...)]``. We
assert the MODEL-FACING ``tool_call_schema`` (excludes injected args) and drive
at least one read + one write tool through a real ``ToolNode`` to prove
injection actually resolves ``trip_id`` from graph state.
"""

import inspect
import json

import pytest
from app.agents.state import TravelAgentState
from langchain_core.messages import AIMessage
from langchain_core.tools import ToolException
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command
from pydantic import ValidationError


def _facing(tool):
    """Model-facing schema fields (injected args stripped)."""
    return tool.tool_call_schema.model_fields


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


def test_get_trip_summary(trip_id):
    from app.tools.trip_tools import get_trip_summary

    out = get_trip_summary.invoke({"trip_id": trip_id, "user_id": "test-user-1"})
    assert out["id"] == trip_id
    assert "budget" in out or "total_spent" in out


def test_get_trip_summary_not_found(agent_db):
    from app.tools.trip_tools import get_trip_summary

    with pytest.raises(ToolException):
        get_trip_summary.invoke({"trip_id": "missing", "user_id": "test-user-1"})


def test_add_itinerary_item(trip_id):
    from app.tools.trip_tools import add_itinerary_item

    out = add_itinerary_item.invoke(
        {
            "trip_id": trip_id,
            "user_id": "test-user-1",
            "day": 1,
            "title": "Senso-ji",
            "status": "booked",
            "notes": "arrive early",
        }
    )
    assert out["title"] == "Senso-ji"
    assert out["status"] == "booked"


def test_add_itinerary_item_bad_status_raises(trip_id):
    # Caught by the annotated `status` field (validated by LangChain's
    # ToolNode against the auto-derived schema before invoke), not the tool
    # body's ValueError catch.
    from app.tools.trip_tools import add_itinerary_item

    with pytest.raises(ValidationError):
        add_itinerary_item.invoke(
            {
                "trip_id": trip_id,
                "user_id": "test-user-1",
                "day": 1,
                "title": "x",
                "status": "nonsense",
            }
        )


def test_get_trip_budget(trip_id):
    from app.tools.trip_tools import get_trip_budget

    out = get_trip_budget.invoke({"trip_id": trip_id, "user_id": "test-user-1"})
    assert isinstance(out, dict)


def test_trip_tools_model_facing_schema_excludes_trip_id():
    from app.tools.trip_tools import (
        add_itinerary_item,
        add_place_to_trip,
        get_trip_budget,
        get_trip_summary,
        list_trip_places,
    )

    for t in (
        get_trip_summary,
        get_trip_budget,
        list_trip_places,
        add_place_to_trip,
        add_itinerary_item,
    ):
        assert "trip_id" not in _facing(t), t.name


def test_trip_id_remains_in_function_signature():
    """The Annotated[..., InjectedState] trip_id param must still be present on
    the underlying function so LangGraph's ToolNode can inject it at call
    time — only the model-facing schema excludes it.
    """
    from app.tools.trip_tools import (
        add_itinerary_item,
        add_place_to_trip,
        get_trip_budget,
        get_trip_summary,
        list_trip_places,
    )

    for t in (
        get_trip_summary,
        get_trip_budget,
        list_trip_places,
        add_place_to_trip,
        add_itinerary_item,
    ):
        assert "trip_id" in inspect.signature(t.func).parameters, t.name


def test_add_place_to_trip_schema_lists_source_values():
    from app.tools.trip_tools import add_place_to_trip

    schema_json = json.dumps(add_place_to_trip.get_input_schema().model_json_schema())
    assert "catalog" in schema_json
    assert "saved" in schema_json


def test_add_itinerary_item_schema_lists_kind_and_status_values():
    from app.tools.trip_tools import add_itinerary_item

    schema_json = json.dumps(add_itinerary_item.get_input_schema().model_json_schema())
    for value in ["place", "activity", "meal", "transport", "note"]:
        assert value in schema_json
    for value in ["pending", "booked", "constraint", "optional"]:
        assert value in schema_json


def test_add_itinerary_item_invalid_kind_raises_on_invoke(trip_id):
    from app.tools.trip_tools import add_itinerary_item

    with pytest.raises(ValidationError):
        add_itinerary_item.invoke(
            {
                "type": "tool_call",
                "id": "t1",
                "name": "add_itinerary_item",
                "args": {
                    "trip_id": trip_id,
                    "day": 1,
                    "title": "x",
                    "kind": "not-a-kind",
                },
            }
        )


def test_get_trip_summary_injected_via_tool_node(trip_id):
    """Prove trip_id resolves via InjectedState through a real ToolNode (read tool)."""
    from app.tools.trip_tools import get_trip_summary

    compiled = _tool_node_graph(get_trip_summary)
    ai_msg = AIMessage(
        content="",
        tool_calls=[{"name": "get_trip_summary", "args": {}, "id": "call-1"}],
    )
    result = compiled.invoke(
        {"messages": [ai_msg], "trip_id": trip_id, "user_id": "test-user-1"}
    )
    tool_msgs = [m for m in result["messages"] if m.__class__.__name__ == "ToolMessage"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].status != "error"
    payload = json.loads(tool_msgs[0].content)
    assert payload["id"] == trip_id


def test_add_itinerary_item_injected_via_tool_node(trip_id):
    """Prove trip_id resolves via InjectedState through a real ToolNode (write tool)."""
    from app.tools.trip_tools import add_itinerary_item

    compiled = _tool_node_graph(add_itinerary_item)
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "add_itinerary_item",
                "args": {"day": 2, "title": "Ben Thanh Market"},
                "id": "call-2",
            }
        ],
    )
    result = compiled.invoke(
        {"messages": [ai_msg], "trip_id": trip_id, "user_id": "test-user-1"}
    )
    tool_msgs = [m for m in result["messages"] if m.__class__.__name__ == "ToolMessage"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].status != "error"
    payload = json.loads(tool_msgs[0].content)
    assert payload["title"] == "Ben Thanh Market"


def test_create_trip_returns_command_with_new_trip_id_and_message(agent_db):
    from app.tools.trip_tools import create_trip

    result = create_trip.invoke(
        {
            "type": "tool_call",
            "id": "call-create-1",
            "name": "create_trip",
            "args": {
                "title": "Da Nang long weekend",
                "city": "Da Nang",
                "user_id": "test-user-1",
            },
        }
    )
    assert isinstance(result, Command)
    new_trip_id = result.update["trip_id"]
    assert isinstance(new_trip_id, str) and new_trip_id

    messages = result.update["messages"]
    assert len(messages) == 1
    msg = messages[0]
    assert msg.__class__.__name__ == "ToolMessage"
    assert msg.tool_call_id == "call-create-1"
    payload = json.loads(msg.content)
    assert payload["id"] == new_trip_id
    assert payload["title"] == "Da Nang long weekend"


def test_create_trip_not_in_trip_tools():
    from app.tools.trip_tools import TRIP_TOOLS, create_trip

    assert create_trip not in TRIP_TOOLS
