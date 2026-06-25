"""Tool registry + weather/memory tools (specs/travel-agent Task 3.4)."""

import pytest


def test_get_tools_for_groups():
    from app.tools.registry import get_tools_for

    planner = {t.name for t in get_tools_for("planner")}
    assert "get_trip_summary" in planner
    assert "search_flights" in planner

    concierge = {t.name for t in get_tools_for("concierge")}
    assert "get_weather" in concierge
    assert "search_places" in concierge

    journal = {t.name for t in get_tools_for("journal")}
    assert "save_user_preference" in journal

    budget = {t.name for t in get_tools_for("budget")}
    assert "add_expense" in budget
    assert "get_trip_budget" in budget

    assert get_tools_for("nope") == []


def test_tool_metadata_annotations():
    from app.tools.registry import TOOL_METADATA

    assert TOOL_METADATA["get_trip_summary"] == {"readOnly": True, "destructive": False}
    assert TOOL_METADATA["add_expense"]["readOnly"] is False
    assert TOOL_METADATA["book_hotel"]["destructive"] is True


def test_all_tools_deduped():
    from app.tools.registry import ALL_TOOLS

    names = [t.name for t in ALL_TOOLS]
    assert len(names) == len(set(names))  # no duplicates


def test_memory_tool_hides_injected_store():
    from app.tools.memory_tools import save_user_preference

    # InjectedStore must NOT appear in the LLM-visible args schema.
    assert "store" not in save_user_preference.args
    assert "user_id" in save_user_preference.args


def test_weather_tool_maps_upstream_error(monkeypatch):
    import asyncio

    from app.exceptions import WeatherUnavailableError
    from app.services import weather_service
    from app.tools.weather_tools import get_weather
    from langchain_core.tools import ToolException

    async def boom(city, days=None):
        raise WeatherUnavailableError("open-meteo down")

    monkeypatch.setattr(weather_service, "get_weather", boom)
    with pytest.raises(ToolException):
        asyncio.run(get_weather.ainvoke({"city": "Tokyo"}))


def test_weather_tool_returns_dump(monkeypatch):
    import asyncio

    from app.services import weather_service
    from app.tools.weather_tools import get_weather
    from pydantic import BaseModel

    class FakeResp(BaseModel):
        city: str
        days: list

    async def ok(city, days=None):
        return FakeResp(city="Tokyo", days=[])

    monkeypatch.setattr(weather_service, "get_weather", ok)
    out = asyncio.run(get_weather.ainvoke({"city": "Tokyo"}))
    assert out == {"city": "Tokyo", "days": []}
