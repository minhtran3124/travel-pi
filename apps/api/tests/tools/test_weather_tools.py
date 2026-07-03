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


def test_get_packing_schema_city_required_days_optional():
    schema = get_packing.get_input_schema().model_json_schema()
    assert schema["required"] == ["city"]
    assert "days" in schema["properties"]
    assert "city" in schema["properties"]


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
