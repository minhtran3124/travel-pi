"""Weather & air-quality tools (specs/travel-agent Task 3.4).

These wrap the async weather/air-quality services (the one real outbound call in
the backend), so the tools are async too. Upstream failures map to
``ToolException`` for self-correction.
"""

from __future__ import annotations

from langchain_core.tools import ToolException, tool

from app.exceptions import AppError
from app.services import air_quality_service, weather_service
from app.tools._base import dump


@tool
async def get_weather(city: str, days: int | None = None) -> dict:
    """Get the multi-day weather forecast for a city (temps, conditions, score)."""
    try:
        return dump(await weather_service.get_weather(city, days))
    except AppError as e:
        raise ToolException(str(e)) from e


@tool
async def get_packing(city: str, days: int | None = None) -> dict:
    """Get a weather-driven packing suggestion for a city over the next days."""
    try:
        return dump(await weather_service.get_packing(city, days))
    except AppError as e:
        raise ToolException(str(e)) from e


@tool
async def get_air_quality(city: str) -> dict:
    """Get the current air-quality forecast (US AQI + category) for a city."""
    try:
        return dump(await air_quality_service.get_air_quality(city))
    except AppError as e:
        raise ToolException(str(e)) from e


WEATHER_TOOLS = [get_weather, get_packing, get_air_quality]
