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


def test_memory_tool_hides_injected_store_and_user_id():
    from app.tools.memory_tools import save_user_preference

    # InjectedStore + InjectedState must NOT appear in the LLM-visible args schema
    # (the model supplies only the semantic args; user_id comes from graph state — C3).
    assert "store" not in save_user_preference.args
    assert "user_id" not in save_user_preference.args
    assert "key" in save_user_preference.args
    assert "text" in save_user_preference.args


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


def test_weather_tool_returns_panel(monkeypatch):
    """get_weather is panel-capable: a ToolCall yields a ToolMessage whose
    ``.content`` is the model-facing summary and ``.artifact`` is the
    ``{"kind":"weather","data":...}`` side-panel payload (specs/agent-side-panel).
    """
    import asyncio

    from app.schemas.weather import (
        CurrentWeather,
        DailyForecast,
        WeatherLocation,
        WeatherResponse,
    )
    from app.services import weather_service
    from app.tools.weather_tools import get_weather
    from langchain_core.messages import ToolMessage

    async def ok(city, days=None):
        return WeatherResponse(
            location=WeatherLocation(
                name="Tokyo",
                country="Japan",
                latitude=35.6,
                longitude=139.7,
                timezone="Asia/Tokyo",
            ),
            current=CurrentWeather(
                time="2026-06-30T00:00",
                temperature_c=24.6,
                apparent_temperature_c=25.1,
                relative_humidity=70,
                wind_speed_kmh=8.0,
                weather_code=2,
                description="Partly cloudy",
            ),
            daily=[
                DailyForecast(
                    date="2026-06-30",
                    temp_min_c=20.0,
                    temp_max_c=27.0,
                    precipitation_probability_max=30,
                    weather_code=2,
                    description="Partly cloudy",
                )
            ],
        )

    monkeypatch.setattr(weather_service, "get_weather", ok)
    msg = asyncio.run(
        get_weather.ainvoke(
            {
                "type": "tool_call",
                "id": "t1",
                "name": "get_weather",
                "args": {"city": "Tokyo"},
            }
        )
    )
    assert isinstance(msg, ToolMessage)
    # Model-facing summary: a short non-empty string carrying the forecast.
    assert isinstance(msg.content, str) and "Tokyo" in msg.content
    # Side-panel artifact carries the rich weather data.
    assert msg.artifact["kind"] == "weather"
    data = msg.artifact["data"]
    assert data["location_name"] == "Tokyo"
    assert data["current"]["emoji"] and data["current"]["condition"] == "partly"
    assert data["daily"][0]["precipitation_probability_max"] == 30


def test_air_quality_tool_returns_panel(monkeypatch):
    """get_air_quality is panel-capable: a ToolCall yields a ToolMessage whose
    ``.artifact`` is the ``{"kind":"air_quality","data":...}`` side-panel payload.
    """
    import asyncio

    from app.schemas.air_quality import AirQualityDay, AirQualityResponse
    from app.schemas.weather import WeatherLocation
    from app.services import air_quality_service
    from app.tools.weather_tools import get_air_quality
    from langchain_core.messages import ToolMessage

    async def ok(city):
        return AirQualityResponse(
            location=WeatherLocation(
                name="Hanoi",
                country="Vietnam",
                latitude=21.0,
                longitude=105.8,
                timezone="Asia/Bangkok",
            ),
            time="2026-06-30T14:00",
            us_aqi=35,
            category="Good",
            pm2_5=8.3,
            attribution="Air quality data by Open-Meteo.com (CC BY 4.0)",
            forecast=[AirQualityDay(date="2026-06-30", max_us_aqi=35, category="Good")],
        )

    monkeypatch.setattr(air_quality_service, "get_air_quality", ok)
    msg = asyncio.run(
        get_air_quality.ainvoke(
            {
                "type": "tool_call",
                "id": "t1",
                "name": "get_air_quality",
                "args": {"city": "Hanoi"},
            }
        )
    )
    assert isinstance(msg, ToolMessage)
    assert isinstance(msg.content, str) and "Hanoi" in msg.content
    assert msg.artifact["kind"] == "air_quality"
    data = msg.artifact["data"]
    assert data["us_aqi"] == 35 and data["band"] == "good" and data["emoji"] == "😊"
    assert len(data["pollutants"]) == 6
    assert data["forecast"][0]["category"] == "Good"
