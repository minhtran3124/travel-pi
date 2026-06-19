"""Tests for GET /air-quality.

Air quality, like weather, makes a real outbound call to Open-Meteo, so every
test monkeypatches ``weather_service._fetch_json`` (which the air-quality
service reuses) to return canned payloads — no network access in the suite.
"""

import pytest
from app.exceptions import WeatherUnavailableError
from app.services import air_quality_service, weather_service

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

# Hourly series engineered so per-day maxima are deterministic:
#   2026-06-16 → max(40, 75) = 75   → Moderate
#   2026-06-17 → max(120, 90) = 120 → Unhealthy for Sensitive Groups
#   2026-06-18 → all null           → None / Unknown
_AIR_QUALITY = {
    "timezone": "Asia/Ho_Chi_Minh",
    "current": {
        "time": "2026-06-16T14:00",
        "us_aqi": 75,
        "pm2_5": 18.3,
        "pm10": 30.1,
        "ozone": 62.4,
        "nitrogen_dioxide": 10.7,
        "sulphur_dioxide": 2.1,
        "carbon_monoxide": 189.5,
    },
    "hourly": {
        "time": [
            "2026-06-16T00:00",
            "2026-06-16T12:00",
            "2026-06-17T00:00",
            "2026-06-17T12:00",
            "2026-06-18T00:00",
            "2026-06-18T12:00",
        ],
        "us_aqi": [40, 75, 120, 90, None, None],
    },
}


def _fake_fetch(geocode_response, air_quality_response=_AIR_QUALITY):
    """Build an async ``_fetch_json`` replacement keyed off the request URL."""

    async def _inner(url: str, params: dict) -> dict:
        if "geocoding" in url:
            return geocode_response
        return air_quality_response

    return _inner


@pytest.fixture()
def mock_open_meteo(monkeypatch):
    """Patch the service so a city resolves and air-quality data comes back."""
    monkeypatch.setattr(weather_service, "_fetch_json", _fake_fetch(_GEOCODE_HIT))


# --- Happy path ---------------------------------------------------------------


def test_air_quality_returns_200(client, mock_open_meteo):
    resp = client.get("/air-quality", params={"city": "Da Nang"})
    assert resp.status_code == 200


def test_air_quality_resolves_location(client, mock_open_meteo):
    body = client.get("/air-quality", params={"city": "Da Nang"}).json()
    assert body["location"]["name"] == "Da Nang"
    assert body["location"]["country"] == "Vietnam"
    assert body["location"]["timezone"] == "Asia/Ho_Chi_Minh"


def test_air_quality_current_pollutants_and_category(client, mock_open_meteo):
    body = client.get("/air-quality", params={"city": "Da Nang"}).json()
    assert body["us_aqi"] == 75
    assert body["category"] == "Moderate"
    assert body["pm2_5"] == 18.3
    assert body["pm10"] == 30.1
    assert body["ozone"] == 62.4
    assert body["nitrogen_dioxide"] == 10.7
    assert body["sulphur_dioxide"] == 2.1
    assert body["carbon_monoxide"] == 189.5
    assert body["time"] == "2026-06-16T14:00"


def test_air_quality_forecast_daily_max(client, mock_open_meteo):
    """Forecast is the per-day max of the hourly series, capped at the horizon."""
    body = client.get("/air-quality", params={"city": "Da Nang"}).json()
    forecast = body["forecast"]
    # air_quality_forecast_days defaults to 3
    assert len(forecast) == 3
    assert forecast[0] == {
        "date": "2026-06-16",
        "max_us_aqi": 75,
        "category": "Moderate",
    }
    assert forecast[1] == {
        "date": "2026-06-17",
        "max_us_aqi": 120,
        "category": "Unhealthy for Sensitive Groups",
    }


def test_air_quality_includes_attribution(client, mock_open_meteo):
    body = client.get("/air-quality", params={"city": "Da Nang"}).json()
    assert body["attribution"] == "Air quality data by Open-Meteo.com (CC BY 4.0)"


# --- Category mapping (unit) --------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (30, "Good"),
        (75, "Moderate"),
        (120, "Unhealthy for Sensitive Groups"),
        (175, "Unhealthy"),
        (250, "Very Unhealthy"),
        (350, "Hazardous"),
        (None, "Unknown"),
        (50, "Good"),  # boundary — inclusive upper bound
        (51, "Moderate"),
    ],
)
def test_us_aqi_category_mapping(value, expected):
    assert air_quality_service._us_aqi_category(value) == expected


def test_air_quality_category_mapping_end_to_end(client, monkeypatch):
    """Each AQI band surfaces the right category via the full request path."""
    bands = {
        30: "Good",
        75: "Moderate",
        120: "Unhealthy for Sensitive Groups",
        175: "Unhealthy",
        250: "Very Unhealthy",
        350: "Hazardous",
    }
    for value, expected in bands.items():
        payload = {
            "timezone": "Asia/Ho_Chi_Minh",
            "current": {"time": "2026-06-16T14:00", "us_aqi": value},
            "hourly": {"time": [], "us_aqi": []},
        }
        monkeypatch.setattr(
            weather_service, "_fetch_json", _fake_fetch(_GEOCODE_HIT, payload)
        )
        body = client.get("/air-quality", params={"city": "Da Nang"}).json()
        assert body["us_aqi"] == value
        assert body["category"] == expected


# --- Null tolerance -----------------------------------------------------------


def test_air_quality_null_current_aqi_is_unknown(client, monkeypatch):
    """A null current us_aqi → category 'Unknown', still 200."""
    payload = {
        "timezone": "Asia/Ho_Chi_Minh",
        "current": {"time": "2026-06-16T14:00", "us_aqi": None, "pm2_5": 5.0},
        "hourly": {"time": [], "us_aqi": []},
    }
    monkeypatch.setattr(
        weather_service, "_fetch_json", _fake_fetch(_GEOCODE_HIT, payload)
    )
    resp = client.get("/air-quality", params={"city": "Da Nang"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["us_aqi"] is None
    assert body["category"] == "Unknown"


def test_air_quality_all_null_forecast_day_no_500(client, mock_open_meteo):
    """A whole all-null forecast day → max_us_aqi None / Unknown, never 500."""
    body = client.get("/air-quality", params={"city": "Da Nang"}).json()
    last = body["forecast"][2]
    assert last["date"] == "2026-06-18"
    assert last["max_us_aqi"] is None
    assert last["category"] == "Unknown"


def test_air_quality_null_pollutant_cells_ok(client, monkeypatch):
    """Null pollutant cells pass through as null, still 200."""
    payload = {
        "timezone": "Asia/Ho_Chi_Minh",
        "current": {
            "time": "2026-06-16T14:00",
            "us_aqi": 42,
            "pm2_5": None,
            "pm10": None,
            "ozone": None,
            "nitrogen_dioxide": None,
            "sulphur_dioxide": None,
            "carbon_monoxide": None,
        },
        "hourly": {"time": [], "us_aqi": []},
    }
    monkeypatch.setattr(
        weather_service, "_fetch_json", _fake_fetch(_GEOCODE_HIT, payload)
    )
    resp = client.get("/air-quality", params={"city": "Da Nang"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["us_aqi"] == 42
    assert body["pm2_5"] is None
    assert body["carbon_monoxide"] is None


# --- Error handling -----------------------------------------------------------


def test_air_quality_missing_current_returns_502(client, monkeypatch):
    """A 200 body missing 'current' / 'time' must surface as 502, not 500."""
    payload = {"timezone": "Asia/Ho_Chi_Minh"}  # no "current"
    monkeypatch.setattr(
        weather_service, "_fetch_json", _fake_fetch(_GEOCODE_HIT, payload)
    )
    resp = client.get("/air-quality", params={"city": "Da Nang"})
    assert resp.status_code == 502


def test_air_quality_unknown_city_returns_404(client, monkeypatch):
    monkeypatch.setattr(weather_service, "_fetch_json", _fake_fetch(_GEOCODE_MISS))
    resp = client.get("/air-quality", params={"city": "Nowhereville"})
    assert resp.status_code == 404
    body = resp.json()
    assert body["status_code"] == 404
    assert body["path"] == "/air-quality"


def test_air_quality_missing_city_param_returns_422(client):
    assert client.get("/air-quality").status_code == 422


def test_air_quality_upstream_failure_returns_502(client, monkeypatch):
    async def _boom(url, params):
        if "geocoding" in url:
            return _GEOCODE_HIT
        raise WeatherUnavailableError("connection timed out")

    monkeypatch.setattr(weather_service, "_fetch_json", _boom)
    resp = client.get("/air-quality", params={"city": "Da Nang"})
    assert resp.status_code == 502
