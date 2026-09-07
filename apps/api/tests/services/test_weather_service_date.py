"""Tests for the optional ``date`` parameter on ``get_weather``/``get_packing``.

MIN-66 / specs/weather-trip-date-accuracy: asking about weather on a
far-future date used to silently return today's forecast. These tests cover
the three behaviors from Task 1.1:

- ``date=None`` is byte-identical to the pre-existing behavior (still sends
  ``forecast_days``, never ``start_date``/``end_date``).
- An in-range ``date`` narrows the Open-Meteo query to that single day via
  ``start_date``/``end_date``.
- An out-of-horizon ``date`` raises ``DomainValidationError`` instead of
  falling back to today, and names ``get_climate`` as the alternative.

Hermetic: ``weather_service._fetch_json`` is monkeypatched, modelled on
``tests/api/weather/test_climate.py``. No network calls are made. The
autouse ``_clear_geocode_cache`` fixture in ``tests/conftest.py`` keeps
geocode lookups isolated between cases.
"""

import asyncio
import datetime

import pytest
from app.exceptions import DomainValidationError
from app.services import weather_service

_GEOCODE_HIT = {
    "results": [
        {
            "name": "Da Nang",
            "country": "Vietnam",
            "latitude": 16.07,
            "longitude": 108.22,
        }
    ]
}

_FORECAST_RESPONSE = {
    "timezone": "Asia/Ho_Chi_Minh",
    "current": {
        "time": "2026-07-20T12:00",
        "temperature_2m": 30.0,
        "apparent_temperature": 33.0,
        "relative_humidity_2m": 70,
        "wind_speed_10m": 10.0,
        "weather_code": 1,
    },
    "daily": {
        "time": ["2026-07-20"],
        "temperature_2m_max": [33.0],
        "temperature_2m_min": [26.0],
        "precipitation_probability_max": [10],
        "weather_code": [1],
    },
}


def _fake_fetch(captured_params):
    """Return an async ``_fetch_json`` stand-in recording forecast params.

    Geocode requests (``"name"`` in params) are answered from ``_GEOCODE_HIT``
    without being recorded; forecast requests are recorded and answered from
    ``_FORECAST_RESPONSE``.
    """

    async def _inner(url: str, params: dict) -> dict:
        if "name" in params:
            return _GEOCODE_HIT
        captured_params.append(params)
        return _FORECAST_RESPONSE

    return _inner


def test_date_none_uses_forecast_days_unchanged(monkeypatch):
    """No ``date`` → still sends ``forecast_days``, never a dated window."""
    captured: list[dict] = []
    monkeypatch.setattr(weather_service, "_fetch_json", _fake_fetch(captured))

    asyncio.run(weather_service.get_weather("Da Nang", days=3))

    assert len(captured) == 1
    params = captured[0]
    assert params["forecast_days"] == 3
    assert "start_date" not in params
    assert "end_date" not in params


def test_in_range_date_narrows_window(monkeypatch):
    """A date within the forecast horizon sends a single-day start/end window."""
    captured: list[dict] = []
    monkeypatch.setattr(weather_service, "_fetch_json", _fake_fetch(captured))

    today = datetime.datetime.now(datetime.timezone.utc).date()
    target = today + datetime.timedelta(days=5)

    asyncio.run(weather_service.get_weather("Da Nang", date=target))

    assert len(captured) == 1
    params = captured[0]
    assert params["start_date"] == target.isoformat()
    assert params["end_date"] == target.isoformat()
    assert "forecast_days" not in params


def test_out_of_range_date_raises_domain_validation_error(monkeypatch):
    """A date beyond the horizon raises instead of falling back to today."""
    captured: list[dict] = []
    monkeypatch.setattr(weather_service, "_fetch_json", _fake_fetch(captured))

    today = datetime.datetime.now(datetime.timezone.utc).date()
    far_future = today + datetime.timedelta(
        days=weather_service._FORECAST_HORIZON_DAYS + 5
    )

    with pytest.raises(DomainValidationError) as exc_info:
        asyncio.run(weather_service.get_weather("Da Nang", date=far_future))

    message = f"{exc_info.value.detail} {exc_info.value.hint or ''}".lower()
    assert "climate" in message
    assert not captured, "must never reach the forecast call for an out-of-range date"


def test_get_packing_forwards_date(monkeypatch):
    """``get_packing`` still delegates to ``get_weather``, now with ``date``."""
    captured: list[dict] = []
    monkeypatch.setattr(weather_service, "_fetch_json", _fake_fetch(captured))

    today = datetime.datetime.now(datetime.timezone.utc).date()
    target = today + datetime.timedelta(days=2)

    asyncio.run(weather_service.get_packing("Da Nang", date=target))

    assert len(captured) == 1
    params = captured[0]
    assert params["start_date"] == target.isoformat()
    assert params["end_date"] == target.isoformat()
