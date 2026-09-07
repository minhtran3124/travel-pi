"""Unit tests for weather scoring and packing derivation.

All tests are network-free: DailyForecast objects are built directly and
get_weather is monkeypatched for the async get_packing tests.
"""

import asyncio

from app.schemas.weather import (
    CurrentWeather,
    DailyForecast,
    WeatherLocation,
    WeatherResponse,
)
from app.services import weather_service
from app.services.weather_service import (
    _code_severity,
    compute_weather_score,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _day(
    *,
    temp_min_c: float,
    temp_max_c: float,
    weather_code: int = 0,
    precipitation_probability_max: int | None = 0,
    date: str = "2026-06-17",
) -> DailyForecast:
    return DailyForecast(
        date=date,
        temp_min_c=temp_min_c,
        temp_max_c=temp_max_c,
        weather_code=weather_code,
        precipitation_probability_max=precipitation_probability_max,
        description=weather_service.describe_code(weather_code),
    )


_LOCATION = WeatherLocation(
    name="TestCity",
    country="Testland",
    latitude=0.0,
    longitude=0.0,
    timezone="UTC",
)

_CURRENT = CurrentWeather(
    time="2026-06-17T10:00",
    temperature_c=22.0,
    apparent_temperature_c=21.0,
    relative_humidity=50,
    wind_speed_kmh=10.0,
    weather_code=0,
    description="Clear sky",
)


def _fake_weather_response(daily: list[DailyForecast]) -> WeatherResponse:
    return WeatherResponse(
        location=_LOCATION,
        current=_CURRENT,
        daily=daily,
    )


# ---------------------------------------------------------------------------
# _code_severity
# ---------------------------------------------------------------------------


def test_code_severity_clear():
    assert _code_severity(0) == 0.0


def test_code_severity_thunderstorm():
    assert _code_severity(95) == 1.0


def test_code_severity_unknown_defaults():
    assert _code_severity(1234) == 0.5


# ---------------------------------------------------------------------------
# compute_weather_score
# ---------------------------------------------------------------------------


def test_score_warm_clear_day():
    """Warm (mean 22°C), clear (code 0), no precip → perfect 1.0."""
    day = _day(
        temp_min_c=20, temp_max_c=24, weather_code=0, precipitation_probability_max=0
    )
    assert compute_weather_score(day) == 1.0


def test_score_cold_thunderstorm():
    """Cold (mean -2.5°C), thunderstorm, heavy precip → below 0.3."""
    day = _day(
        temp_min_c=-5, temp_max_c=0, weather_code=95, precipitation_probability_max=90
    )
    assert compute_weather_score(day) < 0.3


def test_score_clamps_to_zero_one():
    """Score never escapes [0, 1] for extreme inputs."""
    # Extreme cold, worst code, max precip
    day = _day(
        temp_min_c=-100,
        temp_max_c=-90,
        weather_code=99,
        precipitation_probability_max=100,
    )
    score = compute_weather_score(day)
    assert 0.0 <= score <= 1.0

    # Extreme hot, clear, no precip
    day2 = _day(
        temp_min_c=60, temp_max_c=70, weather_code=0, precipitation_probability_max=0
    )
    score2 = compute_weather_score(day2)
    assert 0.0 <= score2 <= 1.0


def test_score_none_precipitation_treated_as_zero():
    """precipitation_probability_max=None must not raise and behaves like 0."""
    day_none = _day(
        temp_min_c=20, temp_max_c=24, weather_code=0, precipitation_probability_max=None
    )
    day_zero = _day(
        temp_min_c=20, temp_max_c=24, weather_code=0, precipitation_probability_max=0
    )
    assert compute_weather_score(day_none) == compute_weather_score(day_zero)


# ---------------------------------------------------------------------------
# get_packing (async, monkeypatched)
# ---------------------------------------------------------------------------


def test_get_packing_overall_low_high_and_rainy_days(monkeypatch):
    """overall_low/high and rainy_days are derived correctly from daily data."""
    daily = [
        _day(
            temp_min_c=30,
            temp_max_c=35,
            weather_code=0,
            precipitation_probability_max=5,
            date="2026-06-17",
        ),  # hot, clear
        _day(
            temp_min_c=25,
            temp_max_c=32,
            weather_code=61,
            precipitation_probability_max=70,
            date="2026-06-18",
        ),  # rainy
    ]
    fake_resp = _fake_weather_response(daily)

    async def _mock_get_weather(city, days=None, date=None):
        return fake_resp

    monkeypatch.setattr(weather_service, "get_weather", _mock_get_weather)

    result = asyncio.run(weather_service.get_packing("TestCity"))

    assert result.overall_low_c == 25.0
    assert result.overall_high_c == 35.0
    assert result.rainy_days == 1
    assert result.days == 2


def test_get_packing_rain_gear_category_present(monkeypatch):
    """Rain gear suggestion is included when a rainy day exists."""
    daily = [
        _day(
            temp_min_c=20,
            temp_max_c=26,
            weather_code=61,
            precipitation_probability_max=80,
            date="2026-06-17",
        ),
    ]
    fake_resp = _fake_weather_response(daily)

    async def _mock_get_weather(city, days=None, date=None):
        return fake_resp

    monkeypatch.setattr(weather_service, "get_weather", _mock_get_weather)

    result = asyncio.run(weather_service.get_packing("TestCity"))

    categories = [s.category for s in result.suggestions]
    assert "Rain gear" in categories
    assert len(result.suggestions) > 0


def test_get_packing_no_rain_gear_when_dry(monkeypatch):
    """Rain gear is omitted when all days are dry."""
    daily = [
        _day(
            temp_min_c=20,
            temp_max_c=25,
            weather_code=0,
            precipitation_probability_max=5,
            date="2026-06-17",
        ),
    ]
    fake_resp = _fake_weather_response(daily)

    async def _mock_get_weather(city, days=None, date=None):
        return fake_resp

    monkeypatch.setattr(weather_service, "get_weather", _mock_get_weather)

    result = asyncio.run(weather_service.get_packing("TestCity"))

    categories = [s.category for s in result.suggestions]
    assert "Rain gear" not in categories


def test_get_packing_essentials_always_present(monkeypatch):
    """Essentials suggestion is always included."""
    daily = [
        _day(
            temp_min_c=22,
            temp_max_c=28,
            weather_code=0,
            precipitation_probability_max=0,
            date="2026-06-17",
        ),
    ]
    fake_resp = _fake_weather_response(daily)

    async def _mock_get_weather(city, days=None, date=None):
        return fake_resp

    monkeypatch.setattr(weather_service, "get_weather", _mock_get_weather)

    result = asyncio.run(weather_service.get_packing("TestCity"))

    categories = [s.category for s in result.suggestions]
    assert "Essentials" in categories


def test_get_packing_hot_days_cold_nights_suggests_both(monkeypatch):
    """A destination that is hot by day and cold at night gets both hot-weather
    clothing and warm layers (the branches are independent, not exclusive)."""
    daily = [
        _day(
            temp_min_c=5,
            temp_max_c=32,
            weather_code=0,
            precipitation_probability_max=0,
            date="2026-06-17",
        ),
    ]
    fake_resp = _fake_weather_response(daily)

    async def _mock_get_weather(city, days=None, date=None):
        return fake_resp

    monkeypatch.setattr(weather_service, "get_weather", _mock_get_weather)

    result = asyncio.run(weather_service.get_packing("TestCity"))

    categories = [s.category for s in result.suggestions]
    assert "Hot-weather clothing" in categories
    assert "Warm layers" in categories
    assert "Mild-weather clothing" not in categories
