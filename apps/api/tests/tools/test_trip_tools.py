"""Trip & itinerary tools (specs/travel-agent Task 3.1)."""

import pytest
from langchain_core.tools import ToolException


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
    from app.tools.trip_tools import add_itinerary_item

    with pytest.raises(ToolException):
        add_itinerary_item.invoke(
            {"trip_id": trip_id, "day": 1, "title": "x", "status": "nonsense"}
        )


def test_get_trip_budget(trip_id):
    from app.tools.trip_tools import get_trip_budget

    out = get_trip_budget.invoke({"trip_id": trip_id})
    assert isinstance(out, dict)
