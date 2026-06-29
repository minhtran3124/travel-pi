"""Weather & air-quality tools (specs/travel-agent Task 3.4).

These wrap the async weather/air-quality services (the one real outbound call in
the backend), so the tools are async too. Upstream failures map to
``ToolException`` for self-correction.
"""

from __future__ import annotations

from langchain_core.tools import ToolException, tool

from app.exceptions import AppError
from app.schemas.weather import WeatherResponse
from app.services import air_quality_service, weather_service
from app.streaming.panels import WeatherPanel
from app.tools._base import dump, panel_result


def _weather_summary(r: WeatherResponse) -> str:
    """Compact textual forecast the model reads (the full data rides the panel).

    Unlike the route tool — where the model only needs the headline — the agent
    often reasons over the forecast (will it rain on day 3?), so the summary
    keeps the per-day lines while the structured payload goes to the drawer.
    """
    where = r.location.name
    if r.location.country:
        where = f"{where}, {r.location.country}"
    c = r.current
    lines = [
        f"{where} ({r.location.timezone}) — weather:",
        f"Now: {c.temperature_c:.0f}°C, {c.description}, feels like "
        f"{c.apparent_temperature_c:.0f}°C, humidity {c.relative_humidity}%, "
        f"wind {c.wind_speed_kmh:.0f} km/h.",
    ]
    for d in r.daily:
        precip = (
            f", precip {d.precipitation_probability_max}%"
            if d.precipitation_probability_max is not None
            else ""
        )
        lines.append(
            f"{d.date}: {d.temp_min_c:.0f}–{d.temp_max_c:.0f}°C, "
            f"{d.description}{precip}."
        )
    return "\n".join(lines)


@tool(response_format="content_and_artifact")
async def get_weather(city: str, days: int | None = None):
    """Get the multi-day weather forecast for a city (temps, conditions, score)."""
    try:
        r = await weather_service.get_weather(city, days)
    except AppError as e:
        raise ToolException(str(e)) from e
    return panel_result(
        _weather_summary(r),
        kind="weather",
        data=WeatherPanel.from_weather_response(r),
    )


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
