"""Tests for weather tools' args_schema (specs/standardize-tool-args-schema Task 3.2).

Schema-only assertions — these tools hit the live Open-Meteo client, so we never
invoke them here (keeps the suite network-free and <60s).
"""

import asyncio

import pytest
from app.exceptions import CityNotFoundError, UpstreamError, WeatherUnavailableError
from app.tools.weather_tools import (
    GetAirQualityArgs,
    GetPackingArgs,
    GetWeatherArgs,
    get_air_quality,
    get_packing,
    get_weather,
)
from langchain_core.tools import ToolException


def test_get_weather_has_hand_authored_args_schema():
    assert get_weather.args_schema is GetWeatherArgs
    assert get_weather.args_schema.__module__.startswith("app.tools")


def test_get_packing_has_hand_authored_args_schema():
    assert get_packing.args_schema is GetPackingArgs
    assert get_packing.args_schema.__module__.startswith("app.tools")


def test_get_air_quality_has_hand_authored_args_schema():
    assert get_air_quality.args_schema is GetAirQualityArgs
    assert get_air_quality.args_schema.__module__.startswith("app.tools")


def test_get_weather_schema_city_required_days_optional():
    schema = get_weather.get_input_schema().model_json_schema()
    assert schema["required"] == ["city"]
    assert "days" in schema["properties"]
    assert "city" in schema["properties"]
    assert "date" in schema["properties"]
    assert schema["properties"]["date"].get("description")


def test_get_packing_schema_city_required_days_optional():
    schema = get_packing.get_input_schema().model_json_schema()
    assert schema["required"] == ["city"]
    assert "days" in schema["properties"]
    assert "city" in schema["properties"]
    assert "date" in schema["properties"]
    assert schema["properties"]["date"].get("description")


def test_get_air_quality_schema_only_city():
    schema = get_air_quality.get_input_schema().model_json_schema()
    assert schema["required"] == ["city"]
    assert set(schema["properties"]) == {"city"}


def test_get_weather_reraises_upstream(monkeypatch):
    from app.tools import weather_tools

    async def boom(*a, **k):
        raise WeatherUnavailableError("open-meteo down")

    monkeypatch.setattr(weather_tools.weather_service, "get_weather", boom)
    with pytest.raises(UpstreamError):
        asyncio.run(weather_tools.get_weather.ainvoke({"city": "Paris"}))


def test_get_weather_wraps_logic(monkeypatch):
    from app.tools import weather_tools

    async def boom(*a, **k):
        raise CityNotFoundError("nope")

    monkeypatch.setattr(weather_tools.weather_service, "get_weather", boom)
    with pytest.raises(ToolException):
        asyncio.run(weather_tools.get_weather.ainvoke({"city": "Xyzzy"}))


def _make_weather_response(city: str, dates: list[str]):
    from app.schemas.weather import (
        CurrentWeather,
        DailyForecast,
        WeatherLocation,
        WeatherResponse,
    )

    return WeatherResponse(
        location=WeatherLocation(
            name=city, latitude=1.0, longitude=1.0, timezone="UTC"
        ),
        current=CurrentWeather(
            time="2026-07-20T00:00",
            temperature_c=25.0,
            apparent_temperature_c=25.0,
            relative_humidity=50,
            wind_speed_kmh=5.0,
            weather_code=0,
            description="Clear sky",
        ),
        daily=[
            DailyForecast(
                date=d,
                temp_min_c=20.0,
                temp_max_c=27.0,
                precipitation_probability_max=0,
                weather_code=0,
                description="Clear sky",
            )
            for d in dates
        ],
    )


def test_weather_summary_states_covered_date_range():
    from app.tools.weather_tools import _weather_summary

    r = _make_weather_response("Kyoto", ["2026-09-01", "2026-09-02", "2026-09-03"])
    summary = _weather_summary(r)
    assert "2026-09-01 to 2026-09-03" in summary


def test_weather_summary_states_single_covered_date():
    from app.tools.weather_tools import _weather_summary

    r = _make_weather_response("Kyoto", ["2026-09-01"])
    summary = _weather_summary(r)
    assert "covering 2026-09-01" in summary


def test_weather_summary_handles_no_forecast_days():
    from app.tools.weather_tools import _weather_summary

    r = _make_weather_response("Kyoto", [])
    summary = _weather_summary(r)
    assert "no forecast days" in summary


def test_get_weather_without_date_omits_date_kwarg(monkeypatch):
    """Backward-compat: date=None must call the service exactly as before —
    a fake with the pre-date-arg signature (city, days=None) must still work."""
    from app.tools import weather_tools

    async def fake(city, days=None):
        return _make_weather_response(city, ["2026-07-20"])

    monkeypatch.setattr(weather_tools.weather_service, "get_weather", fake)
    content = asyncio.run(weather_tools.get_weather.ainvoke({"city": "Kyoto"}))
    assert "Kyoto" in content


def test_get_weather_iso_date_passed_through_as_date_object(monkeypatch):
    from app.tools import weather_tools

    captured: dict = {}

    async def fake(city, **kwargs):
        captured.update(kwargs)
        return _make_weather_response(city, ["2026-09-01"])

    monkeypatch.setattr(weather_tools.weather_service, "get_weather", fake)
    asyncio.run(
        weather_tools.get_weather.ainvoke({"city": "Kyoto", "date": "2026-09-01"})
    )
    assert captured["date"].isoformat() == "2026-09-01"


def test_get_weather_unparseable_date_raises_tool_exception():
    with pytest.raises(ToolException):
        asyncio.run(
            get_weather.ainvoke({"city": "Kyoto", "date": "sometime in September"})
        )


def test_get_packing_iso_date_passed_through(monkeypatch):
    from app.tools import weather_tools

    captured: dict = {}

    async def fake(city, **kwargs):
        captured.update(kwargs)
        return _make_weather_response(city, ["2026-09-01"])

    monkeypatch.setattr(weather_tools.weather_service, "get_weather", fake)
    asyncio.run(
        weather_tools.get_packing.ainvoke({"city": "Kyoto", "date": "2026-09-01"})
    )
    assert captured["date"].isoformat() == "2026-09-01"


def test_get_climate_reachable_in_all_tools_and_planner_and_concierge_domains():
    from app.tools.registry import ALL_TOOLS, get_tools_for

    assert "get_climate" in {t.name for t in ALL_TOOLS}
    assert "get_climate" in {t.name for t in get_tools_for("planner")}
    assert "get_climate" in {t.name for t in get_tools_for("concierge")}
