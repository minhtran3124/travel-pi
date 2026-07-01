"""Trip & itinerary tools (specs/travel-agent Task 3.1).

Task 2.2 (specs/standardize-tool-args-schema) extends this file with
args_schema / enum-in-schema / invalid-value assertions.
"""

import json

import pytest
from langchain_core.tools import ToolException
from pydantic import ValidationError


def test_get_trip_summary(trip_id):
    from app.tools.trip_tools import get_trip_summary

    out = get_trip_summary.invoke({"trip_id": trip_id})
    assert out["id"] == trip_id
    assert "budget" in out or "total_spent" in out


def test_get_trip_summary_not_found(agent_db):
    from app.tools.trip_tools import get_trip_summary

    with pytest.raises(ToolException):
        get_trip_summary.invoke({"trip_id": "missing"})


def test_add_itinerary_item(trip_id):
    from app.tools.trip_tools import add_itinerary_item

    out = add_itinerary_item.invoke(
        {
            "trip_id": trip_id,
            "day": 1,
            "title": "Senso-ji",
            "status": "booked",
            "notes": "arrive early",
        }
    )
    assert out["title"] == "Senso-ji"
    assert out["status"] == "booked"


def test_add_itinerary_item_bad_status_raises(trip_id):
    # Now caught by the AddItineraryItemArgs enum field (validated by LangChain's
    # ToolNode against args_schema before invoke), not the tool body's ValueError
    # catch — see specs/standardize-tool-args-schema Task 2.2.
    from app.tools.trip_tools import add_itinerary_item

    with pytest.raises(ValidationError):
        add_itinerary_item.invoke(
            {"trip_id": trip_id, "day": 1, "title": "x", "status": "nonsense"}
        )


def test_get_trip_budget(trip_id):
    from app.tools.trip_tools import get_trip_budget

    out = get_trip_budget.invoke({"trip_id": trip_id})
    assert isinstance(out, dict)


def test_all_trip_tools_have_args_schema():
    from app.tools.trip_tools import (
        AddItineraryItemArgs,
        AddPlaceToTripArgs,
        GetTripBudgetArgs,
        GetTripSummaryArgs,
        ListTripPlacesArgs,
        add_itinerary_item,
        add_place_to_trip,
        get_trip_budget,
        get_trip_summary,
        list_trip_places,
    )

    assert get_trip_summary.args_schema is GetTripSummaryArgs
    assert get_trip_budget.args_schema is GetTripBudgetArgs
    assert list_trip_places.args_schema is ListTripPlacesArgs
    assert add_place_to_trip.args_schema is AddPlaceToTripArgs
    assert add_itinerary_item.args_schema is AddItineraryItemArgs


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
