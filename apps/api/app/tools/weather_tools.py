"""Weather and air-quality tools wrapping the async weather/air-quality services."""

from __future__ import annotations

from datetime import datetime

from langchain_core.tools import ToolException, tool
from pydantic import Field

from app.core.config import get_settings
from app.core.dates import resolve_travel_date, today_in_timezone
from app.exceptions import AppError, UpstreamError
from app.schemas.air_quality import AirQualityResponse
from app.schemas.base import AppBaseModel
from app.schemas.weather import WeatherResponse
from app.services import air_quality_service, weather_service
from app.streaming.panels import AirQualityPanel, WeatherPanel
from app.tools._base import dump, log_tool_call, panel_result, tool_error

_DATE_DESCRIPTION = (
    "Optional specific date, ISO format YYYY-MM-DD, to get a single day's "
    "forecast for instead of the rolling multi-day window from today. Only "
    "use this for a date within roughly the next 2 weeks (the forecast "
    "horizon) — for a date further out, call get_climate instead, which "
    "returns typical/average monthly conditions rather than a forecast. For "
    "any non-ISO wording (e.g. 'next Friday'), call the resolve_date tool on "
    "the traveller's original expression first — never compute or guess a "
    "date yourself."
)


class GetWeatherArgs(AppBaseModel):
    city: str = Field(..., description="The city to get the forecast for.")
    days: int | None = Field(
        None, description="Number of forecast days (service default when omitted)."
    )
    date: str | None = Field(None, description=_DATE_DESCRIPTION)


class GetPackingArgs(AppBaseModel):
    city: str = Field(..., description="The city to get the packing suggestion for.")
    days: int | None = Field(
        None, description="Number of days to plan for (service default when omitted)."
    )
    date: str | None = Field(None, description=_DATE_DESCRIPTION)


def _resolve_optional_date(raw: str | None):
    """Resolve an optional model-supplied date string: numeric ISO parses directly, other wording must
    have gone through the ``resolve_date`` tool first."""
    if raw is None:
        return None
    today = today_in_timezone(get_settings().agent_timezone)
    try:
        resolved = resolve_travel_date(raw, today)
        return datetime.strptime(resolved, "%Y-%m-%d").date()
    except ValueError as e:
        raise ToolException(
            f"date {raw!r} could not be resolved to a concrete YYYY-MM-DD "
            f"date. Today is {today.isoformat()}. Call the resolve_date tool "
            "on the traveller's original date expression to get a concrete "
            "date — only ask the traveller if resolve_date reports it "
            "ambiguous."
        ) from e


class GetAirQualityArgs(AppBaseModel):
    city: str = Field(..., description="The city to get the air-quality forecast for.")


def _weather_summary(r: WeatherResponse) -> str:
    """Compact textual forecast the model reads; per-day lines are kept because the agent reasons over
    them (will it rain on day 3?) while the full data rides the panel."""
    where = r.location.name
    if r.location.country:
        where = f"{where}, {r.location.country}"
    c = r.current
    if not r.daily:
        covers = "no forecast days"
    elif len(r.daily) == 1:
        covers = r.daily[0].date
    else:
        covers = f"{r.daily[0].date} to {r.daily[-1].date}"
    lines = [
        f"{where} ({r.location.timezone}) — weather forecast covering {covers}:",
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


@tool(args_schema=GetWeatherArgs, response_format="content_and_artifact")
async def get_weather(city: str, days: int | None = None, date: str | None = None):
    """Get the multi-day weather forecast for a city (temps, conditions, score).

    :param city: The city to get the forecast for.
    :param days: Number of forecast days (service default when omitted).
    :param date: Optional single date (YYYY-MM-DD) to fetch instead of the
        rolling ``days``-long window. Only valid within the forecast horizon
        (~2 weeks) — use ``get_climate`` for dates further out.
    :return: A ``(summary, artifact)`` tuple in the LangChain
        ``content_and_artifact`` shape.
    """
    log_tool_call("get_weather", locals())
    parsed_date = _resolve_optional_date(date)
    kwargs = {"days": days}
    if parsed_date is not None:
        kwargs["date"] = parsed_date
    try:
        r = await weather_service.get_weather(city, **kwargs)
    except UpstreamError:
        raise  # transient — let RetryPolicy retry the node
    except AppError as e:
        raise tool_error(e) from e
    return panel_result(
        _weather_summary(r),
        kind="weather",
        data=WeatherPanel.from_weather_response(r),
    )


@tool(args_schema=GetPackingArgs)
async def get_packing(
    city: str, days: int | None = None, date: str | None = None
) -> dict:
    """Get a weather-driven packing suggestion for a city over the next days.

    :param city: The city to get the packing suggestion for.
    :param days: Number of days to plan for (service default when omitted).
    :param date: Optional single date (YYYY-MM-DD) to base suggestions on
        instead of the rolling ``days``-long window. Only valid within the
        forecast horizon (~2 weeks) — use ``get_climate`` for dates further out.
    :return: The packing suggestion.
    """
    log_tool_call("get_packing", locals())
    parsed_date = _resolve_optional_date(date)
    kwargs = {"days": days}
    if parsed_date is not None:
        kwargs["date"] = parsed_date
    try:
        return dump(await weather_service.get_packing(city, **kwargs))
    except UpstreamError:
        raise  # transient — let RetryPolicy retry the node
    except AppError as e:
        raise tool_error(e) from e


def _air_quality_summary(r: AirQualityResponse) -> str:
    """Compact textual AQI reading the model reads (full data rides the panel)."""
    where = r.location.name
    if r.location.country:
        where = f"{where}, {r.location.country}"
    aqi = r.us_aqi if r.us_aqi is not None else "n/a"
    lines = [f"{where}: US AQI {aqi} ({r.category}) at {r.time.replace('T', ' ')}."]
    for d in r.forecast:
        peak = d.max_us_aqi if d.max_us_aqi is not None else "n/a"
        lines.append(f"{d.date}: peak AQI {peak} ({d.category}).")
    return "\n".join(lines)


@tool(args_schema=GetAirQualityArgs, response_format="content_and_artifact")
async def get_air_quality(city: str):
    """Get the current air-quality forecast (US AQI + category) for a city.

    :param city: The city to get the air-quality forecast for.
    :return: A ``(summary, artifact)`` tuple in the LangChain
        ``content_and_artifact`` shape.
    """
    log_tool_call("get_air_quality", locals())
    try:
        r = await air_quality_service.get_air_quality(city)
    except UpstreamError:
        raise  # transient — let RetryPolicy retry the node
    except AppError as e:
        raise tool_error(e) from e
    return panel_result(
        _air_quality_summary(r),
        kind="air_quality",
        data=AirQualityPanel.from_air_quality_response(r),
    )


WEATHER_TOOLS = [get_weather, get_packing, get_air_quality]
