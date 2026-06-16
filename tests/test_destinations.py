"""Tests for GET /destinations/{city}/overview.

All tests are hermetic (offline): the Open-Meteo weather call is
monkeypatched throughout so no real network I/O occurs.
"""

import pytest
from app.exceptions import WeatherUnavailableError
from app.schemas.weather import WeatherResponse
from app.services import weather_service

# ---------------------------------------------------------------------------
# Shared weather stub
# ---------------------------------------------------------------------------

_STUB_WEATHER = WeatherResponse(
    location={  # type: ignore[arg-type]
        "name": "Da Nang",
        "country": "Vietnam",
        "latitude": 16.0544,
        "longitude": 108.2022,
        "timezone": "Asia/Ho_Chi_Minh",
    },
    current={  # type: ignore[arg-type]
        "time": "2026-06-16T10:00",
        "temperature_c": 31.0,
        "apparent_temperature_c": 36.0,
        "relative_humidity": 70,
        "wind_speed_kmh": 12.0,
        "weather_code": 0,
        "description": "Clear sky",
    },
    daily=[],
    attribution="Weather data by Open-Meteo.com (CC BY 4.0)",
)


@pytest.fixture()
def mock_weather(monkeypatch):
    """Replace weather_service.get_weather with a fast async stub."""

    async def _stub(city: str, days: int | None = None) -> WeatherResponse:
        return _STUB_WEATHER

    monkeypatch.setattr(weather_service, "get_weather", _stub)


@pytest.fixture()
def broken_weather(monkeypatch):
    """Replace weather_service.get_weather with one that raises WeatherUnavailableError."""

    async def _fail(city: str, days: int | None = None) -> WeatherResponse:
        raise WeatherUnavailableError("upstream down")

    monkeypatch.setattr(weather_service, "get_weather", _fail)


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


def test_overview_happy_path_status(client, mock_weather):
    resp = client.get("/destinations/Da Nang/overview")
    assert resp.status_code == 200


def test_overview_happy_path_city_fields(client, mock_weather):
    body = client.get("/destinations/Da Nang/overview").json()
    assert body["city"] == "Da Nang"
    assert body["country"] == "Vietnam"
    assert isinstance(body["latitude"], float)
    assert isinstance(body["longitude"], float)


def test_overview_happy_path_top_places_non_empty(client, mock_weather):
    body = client.get("/destinations/Da Nang/overview").json()
    assert len(body["top_places"]) > 0


def test_overview_happy_path_essential_tips_non_empty(client, mock_weather):
    body = client.get("/destinations/Da Nang/overview").json()
    assert len(body["essential_tips"]) > 0


def test_overview_happy_path_hotel_summary(client, mock_weather):
    body = client.get("/destinations/Da Nang/overview").json()
    hs = body["hotel_summary"]
    assert hs is not None
    assert hs["count"] >= 1
    assert isinstance(hs["sample"], list)


def test_overview_happy_path_attribution_set(client, mock_weather):
    body = client.get("/destinations/Da Nang/overview").json()
    assert body["attribution"]


# ---------------------------------------------------------------------------
# 2. Fuzzy resolve — "danang" → "Da Nang"
# ---------------------------------------------------------------------------


def test_overview_fuzzy_resolve_status(client, mock_weather):
    resp = client.get("/destinations/danang/overview")
    assert resp.status_code == 200


def test_overview_fuzzy_resolve_city_name(client, mock_weather):
    body = client.get("/destinations/danang/overview").json()
    assert body["city"] == "Da Nang"


# ---------------------------------------------------------------------------
# 3. Unknown city → 404 with standard error envelope
# ---------------------------------------------------------------------------


def test_overview_unknown_city_status(client, mock_weather):
    resp = client.get("/destinations/Atlantis/overview")
    assert resp.status_code == 404


def test_overview_unknown_city_error_envelope(client, mock_weather):
    body = client.get("/destinations/Atlantis/overview").json()
    for key in ("error", "message", "status_code", "path"):
        assert key in body, f"missing key in error envelope: {key}"


# ---------------------------------------------------------------------------
# 4. include filter — only "places"
# ---------------------------------------------------------------------------


def test_overview_include_places_status(client, mock_weather):
    resp = client.get("/destinations/Da Nang/overview", params={"include": "places"})
    assert resp.status_code == 200


def test_overview_include_places_only(client, mock_weather):
    body = client.get(
        "/destinations/Da Nang/overview", params={"include": "places"}
    ).json()
    assert len(body["top_places"]) > 0
    assert body["weather"] is None
    assert body["hotel_summary"] is None
    assert body["essential_tips"] == []


# ---------------------------------------------------------------------------
# 5. Weather degradation — upstream raises, overview still returns 200
# ---------------------------------------------------------------------------


def test_overview_weather_degradation_status(client, broken_weather):
    resp = client.get("/destinations/Da Nang/overview")
    assert resp.status_code == 200


def test_overview_weather_degradation_weather_null(client, broken_weather):
    body = client.get("/destinations/Da Nang/overview").json()
    assert body["weather"] is None


def test_overview_weather_degradation_rest_present(client, broken_weather):
    body = client.get("/destinations/Da Nang/overview").json()
    # The rest of the overview is still assembled despite the weather failure.
    assert body["city"] == "Da Nang"
    assert len(body["top_places"]) > 0
    assert body["hotel_summary"] is not None


# ---------------------------------------------------------------------------
# 6. place_limit cap
# ---------------------------------------------------------------------------


def test_overview_place_limit_cap(client, mock_weather):
    body = client.get(
        "/destinations/Da Nang/overview",
        params={"include": "places", "place_limit": 2},
    ).json()
    assert len(body["top_places"]) <= 2
