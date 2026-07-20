"""Regression test for MIN-66 / GitHub #97.

Original defect: on 2026-07-20 a traveller asked about a Tokyo trip on
1-3 Sep 2026. ``get_weather(city='Tokyo', days=3)`` ignored the trip dates
and silently returned the 20-22 Jul (today-anchored) forecast; the agent then
reported that as the trip's weather and built a weather-fit itinerary +
packing list (umbrella, waterproof) on top of it. The fix makes a date beyond
the Open-Meteo forecast horizon fail loudly instead of falling back to today,
with ``get_climate`` as the documented alternative for far-future dates.

This test pins that behavior at the deterministic seam the fix lives in —
``weather_tools.get_weather`` (the boundary the agent's ToolNode actually
calls) backed by the real ``weather_service`` with only the network
(``weather_service._fetch_json``) mocked — never model prose, which isn't
deterministic under ``FakeLLM``.

Note on "points at get_climate": the pointer is asserted on the text the model
actually receives. Agent tools surface failures as ``ToolException(str(e))``
and ``AppError.__str__`` returns ``.detail`` alone, so a pointer placed only in
``.hint`` would never reach the model — the recovery text therefore lives in
the exception's detail. ``.hint`` is kept for the HTTP error envelope, which
does carry it, and is asserted separately below so the two cannot silently
drift apart.
"""

import asyncio
import datetime

import pytest
from app.services import weather_service
from app.tools import weather_tools
from app.tools.registry import get_tools_for
from langchain_core.tools import ToolException

_GEOCODE_HIT = {
    "results": [
        {
            "name": "Tokyo",
            "country": "Japan",
            "latitude": 35.68,
            "longitude": 139.69,
        }
    ]
}


def _fake_fetch(captured_forecast_params: list[dict]):
    """Return an async ``_fetch_json`` stand-in modelled on
    ``tests/api/weather/test_climate.py`` / ``tests/services/test_weather_service_date.py``.

    Geocode requests (``"name"`` in params) are answered from ``_GEOCODE_HIT``
    without being recorded; forecast requests are recorded (so tests can
    assert whether Open-Meteo was ever hit) and answered with a response
    dated to whatever window was actually requested — never a hardcoded
    calendar date, so the fixture can't accidentally coincide with "today".
    """

    async def _inner(url: str, params: dict) -> dict:
        if "name" in params:
            return _GEOCODE_HIT
        captured_forecast_params.append(params)
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        forecast_date = params.get("start_date", today)
        return {
            "timezone": "Asia/Tokyo",
            "current": {
                "time": f"{today}T12:00",
                "temperature_2m": 30.0,
                "apparent_temperature": 33.0,
                "relative_humidity_2m": 70,
                "wind_speed_10m": 10.0,
                "weather_code": 1,
            },
            "daily": {
                "time": [forecast_date],
                "temperature_2m_max": [33.0],
                "temperature_2m_min": [26.0],
                "precipitation_probability_max": [10],
                "weather_code": [1],
            },
        }

    return _inner


def test_far_future_trip_date_refuses_instead_of_returning_today(monkeypatch):
    """The MIN-66 defect, reproduced at the tool boundary: asking for weather
    on a date well beyond the forecast horizon must fail loudly and never
    reach Open-Meteo — not silently answer with today's forecast."""
    captured: list[dict] = []
    monkeypatch.setattr(weather_service, "_fetch_json", _fake_fetch(captured))

    today = datetime.datetime.now(datetime.timezone.utc).date()
    far_future = today + datetime.timedelta(
        days=weather_service._FORECAST_HORIZON_DAYS + 30
    )

    with pytest.raises(ToolException) as exc_info:
        asyncio.run(
            weather_tools.get_weather.ainvoke(
                {"city": "Tokyo", "date": far_future.isoformat()}
            )
        )

    # Refuses loudly rather than falling through to a today-anchored call.
    assert not captured, "must never reach Open-Meteo for an out-of-horizon date"

    # The text the MODEL actually receives must name the recovery path. This is
    # the assertion that matters: a pointer the model cannot read is no pointer
    # at all (see module docstring — str(AppError) drops .hint).
    assert "get_climate" in str(exc_info.value)

    # The hint is kept for the HTTP error envelope. Asserted separately so the
    # two surfaces cannot silently drift apart.
    cause = exc_info.value.__cause__
    assert cause is not None
    assert "get_climate" in (cause.hint or "")


def test_get_weather_tool_description_names_get_climate_for_far_dates():
    """The escape hatch is advertised unconditionally in the tool's own
    description (read by the model on every call), not just on failure."""
    assert "get_climate" in weather_tools.get_weather.description


def test_get_climate_is_reachable_in_planner_and_concierge_domains():
    """Prove the escape hatch the error/description names actually exists in
    the agent's toolset — not just as prose."""
    planner_names = {t.name for t in get_tools_for("planner")}
    concierge_names = {t.name for t in get_tools_for("concierge")}
    assert "get_climate" in planner_names
    assert "get_climate" in concierge_names


def test_near_future_trip_date_still_works_and_covers_requested_date(monkeypatch):
    """Guards the opposite failure mode: over-correcting into refusing every
    dated request. A date within the horizon must succeed, and the forecast
    returned must cover the REQUESTED date, not today's."""
    captured: list[dict] = []
    monkeypatch.setattr(weather_service, "_fetch_json", _fake_fetch(captured))

    today = datetime.datetime.now(datetime.timezone.utc).date()
    near_future = today + datetime.timedelta(days=5)

    content = asyncio.run(
        weather_tools.get_weather.ainvoke(
            {"city": "Tokyo", "date": near_future.isoformat()}
        )
    )

    assert len(captured) == 1
    assert captured[0]["start_date"] == near_future.isoformat()
    assert captured[0]["end_date"] == near_future.isoformat()
    assert captured[0]["start_date"] != today.isoformat()

    assert near_future.isoformat() in content
    assert today.isoformat() not in content
