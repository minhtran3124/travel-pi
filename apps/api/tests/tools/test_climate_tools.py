"""Tests for the get_climate tool's args_schema and error contract
(specs/weather-trip-date-accuracy Task 1.2).

Schema-only + mocked-service assertions — never hit the live Open-Meteo
client, keeps the suite network-free and <60s.
"""

import asyncio

import pytest
from app.exceptions import CityNotFoundError, UpstreamError, WeatherUnavailableError
from app.tools.climate_tools import CLIMATE_TOOLS, GetClimateArgs, get_climate
from langchain_core.tools import ToolException


def test_get_climate_has_hand_authored_args_schema():
    assert get_climate.args_schema is GetClimateArgs
    assert get_climate.args_schema.__module__.startswith("app.tools")


def test_get_climate_schema_city_required_month_optional():
    schema = get_climate.get_input_schema().model_json_schema()
    assert schema["required"] == ["city"]
    assert "month" in schema["properties"]
    assert "city" in schema["properties"]


def test_get_climate_in_climate_tools_list():
    assert [get_climate] == CLIMATE_TOOLS


def test_get_climate_reraises_upstream(monkeypatch):
    from app.tools import climate_tools

    async def boom(*a, **k):
        raise WeatherUnavailableError("open-meteo archive down")

    monkeypatch.setattr(climate_tools.climate_service, "get_climate", boom)
    with pytest.raises(UpstreamError):
        asyncio.run(climate_tools.get_climate.ainvoke({"city": "Paris"}))


def test_get_climate_wraps_logic(monkeypatch):
    from app.tools import climate_tools

    async def boom(*a, **k):
        raise CityNotFoundError("nope")

    monkeypatch.setattr(climate_tools.climate_service, "get_climate", boom)
    with pytest.raises(ToolException):
        asyncio.run(climate_tools.get_climate.ainvoke({"city": "Xyzzy"}))
