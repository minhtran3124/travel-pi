"""Tests for GET /weather.

The weather feature is the only part of the backend that makes a real
outbound call, so every test here monkeypatches ``weather_service._fetch_json``
to return canned Open-Meteo payloads — no network access in the suite.
"""

import pytest
from app.exceptions import WeatherUnavailableError
from app.services import weather_service

# --- Canned Open-Meteo payloads ------------------------------------------------

_GEOCODE_HIT = {
    "results": [
        {
            "name": "Da Nang",
            "country": "Vietnam",
            "latitude": 16.06778,
            "longitude": 108.22083,
        }
    ]
}

_GEOCODE_MISS = {"generationtime_ms": 0.1}  # no "results" key — city not found

_FORECAST = {
    "timezone": "Asia/Ho_Chi_Minh",
    "current": {
        "time": "2026-05-14T10:00",
        "temperature_2m": 31.4,
        "apparent_temperature": 37.2,
        "relative_humidity_2m": 70,
        "wind_speed_10m": 12.3,
        "weather_code": 2,
    },
    "daily": {
        "time": ["2026-05-14", "2026-05-15", "2026-05-16"],
        "temperature_2m_max": [33.0, 34.1, 32.5],
        "temperature_2m_min": [26.0, 26.5, 25.8],
        "precipitation_probability_max": [10, 40, 80],
        "weather_code": [2, 61, 95],
    },
}


def _fake_fetch(geocode_response):
    """Build an async ``_fetch_json`` replacement keyed off the request URL."""

    async def _inner(url: str, params: dict) -> dict:
        if "geocoding" in url:
            return geocode_response
        return _FORECAST

    return _inner


@pytest.fixture()
def mock_open_meteo(monkeypatch):
    """Patch the service so a city resolves and a forecast comes back."""
    monkeypatch.setattr(weather_service, "_fetch_json", _fake_fetch(_GEOCODE_HIT))


# --- Happy path ---------------------------------------------------------------


def test_weather_returns_200(client, mock_open_meteo):
    resp = client.get("/weather", params={"city": "Da Nang"})
    assert resp.status_code == 200


def test_weather_resolves_location(client, mock_open_meteo):
    body = client.get("/weather", params={"city": "Da Nang"}).json()
    assert body["location"]["name"] == "Da Nang"
    assert body["location"]["country"] == "Vietnam"
    assert body["location"]["timezone"] == "Asia/Ho_Chi_Minh"


def test_weather_current_conditions(client, mock_open_meteo):
    body = client.get("/weather", params={"city": "Da Nang"}).json()
    current = body["current"]
    assert current["temperature_c"] == 31.4
    assert current["relative_humidity"] == 70
    assert current["weather_code"] == 2
    assert current["description"] == "Partly cloudy"


def test_weather_daily_forecast(client, mock_open_meteo):
    body = client.get("/weather", params={"city": "Da Nang"}).json()
    daily = body["daily"]
    assert len(daily) == 3
    assert daily[0]["date"] == "2026-05-14"
    assert daily[1]["description"] == "Slight rain"
    assert daily[2]["description"] == "Thunderstorm"
    assert daily[2]["precipitation_probability_max"] == 80


def test_weather_includes_attribution(client, mock_open_meteo):
    body = client.get("/weather", params={"city": "Da Nang"}).json()
    assert "Open-Meteo" in body["attribution"]


# --- Error handling -----------------------------------------------------------


def test_weather_unknown_city_returns_404(client, monkeypatch):
    monkeypatch.setattr(weather_service, "_fetch_json", _fake_fetch(_GEOCODE_MISS))
    resp = client.get("/weather", params={"city": "Nowhereville"})
    assert resp.status_code == 404


def test_weather_missing_city_param_returns_422(client):
    assert client.get("/weather").status_code == 422


def test_weather_upstream_failure_returns_502(client, monkeypatch):
    async def _boom(url, params):
        raise WeatherUnavailableError("connection timed out")

    monkeypatch.setattr(weather_service, "_fetch_json", _boom)
    resp = client.get("/weather", params={"city": "Da Nang"})
    assert resp.status_code == 502


def test_weather_malformed_upstream_body_returns_502(client, monkeypatch):
    """A 200 with a body shape we don't recognise must surface as 502, not 500."""

    async def _malformed(url, params):
        if "geocoding" in url:
            return _GEOCODE_HIT
        # Forecast URL: missing the "current" / "daily" keys we expect.
        return {"timezone": "Asia/Ho_Chi_Minh"}

    monkeypatch.setattr(weather_service, "_fetch_json", _malformed)
    resp = client.get("/weather", params={"city": "Da Nang"})
    assert resp.status_code == 502


# --- Unit: WMO code mapping ---------------------------------------------------


def test_describe_code_known_and_unknown():
    assert weather_service.describe_code(0) == "Clear sky"
    assert weather_service.describe_code(95) == "Thunderstorm"
    assert weather_service.describe_code(123456) == "Unknown"
