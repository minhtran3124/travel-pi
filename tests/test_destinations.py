"""Tests for GET /destinations/{city}/overview (composition endpoint)."""

import pytest
from app.exceptions import WeatherUnavailableError
from app.schemas.weather import (
    CurrentWeather,
    DailyForecast,
    WeatherLocation,
    WeatherResponse,
)
from app.services import weather_service


def _fake_weather(city: str, days=None) -> WeatherResponse:
    return WeatherResponse(
        location=WeatherLocation(
            name=city,
            country="Vietnam",
            latitude=16.0,
            longitude=108.0,
            timezone="Asia/Ho_Chi_Minh",
        ),
        current=CurrentWeather(
            time="2026-05-29T12:00",
            temperature_c=30.0,
            apparent_temperature_c=33.0,
            relative_humidity=70,
            wind_speed_kmh=10.0,
            weather_code=1,
            description="Mainly clear",
        ),
        daily=[
            DailyForecast(
                date="2026-05-29",
                temp_min_c=25.0,
                temp_max_c=32.0,
                precipitation_probability_max=20,
                weather_code=1,
                description="Mainly clear",
            )
        ],
    )


@pytest.fixture(autouse=True)
def _stub_weather(monkeypatch):
    """Stub the live weather call so the overview never hits the network."""

    async def fake_get_weather(city, days=None):
        return _fake_weather(city, days)

    monkeypatch.setattr(weather_service, "get_weather", fake_get_weather)


def test_overview_returns_200(client):
    assert client.get("/destinations/Da Nang/overview").status_code == 200


def test_overview_has_all_sections(client):
    body = client.get("/destinations/Da Nang/overview").json()
    for field in (
        "city",
        "country",
        "airports",
        "hotel_count",
        "top_places",
        "essential_tips",
        "weather",
        "summary",
    ):
        assert field in body


def test_overview_resolves_city_fuzzily(client):
    body = client.get("/destinations/danang/overview").json()
    assert body["city"] == "Da Nang"
    assert body["country"] == "Vietnam"


def test_overview_includes_coordinates(client):
    body = client.get("/destinations/Da Nang/overview").json()
    assert body["latitude"] is not None
    assert body["longitude"] is not None


def test_overview_hotel_count_positive(client):
    body = client.get("/destinations/Da Nang/overview").json()
    assert body["hotel_count"] >= 3  # CLAUDE.md: every city has >=3 hotels


def test_overview_top_places_respects_limit(client):
    body = client.get("/destinations/Da Nang/overview", params={"top_places": 2}).json()
    assert len(body["top_places"]) <= 2


def test_overview_top_places_sorted_by_rating_desc(client):
    places = client.get("/destinations/Da Nang/overview").json()["top_places"]
    ratings = [p["rating"] for p in places]
    assert ratings == sorted(ratings, reverse=True)


def test_overview_essential_tips_are_essential(client):
    tips = client.get("/destinations/Da Nang/overview").json()["essential_tips"]
    assert all(t["is_essential"] for t in tips)


def test_overview_includes_weather_when_available(client):
    body = client.get("/destinations/Da Nang/overview").json()
    assert body["weather"] is not None
    assert body["weather"]["current"]["temperature_c"] == 30.0


def test_overview_weather_is_best_effort(client, monkeypatch):
    """An upstream weather failure leaves weather=null but still returns 200."""

    async def boom(city, days=None):
        raise WeatherUnavailableError("Open-Meteo down")

    monkeypatch.setattr(weather_service, "get_weather", boom)
    resp = client.get("/destinations/Da Nang/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert body["weather"] is None
    # The rest of the overview is still populated.
    assert body["hotel_count"] >= 3
    assert body["top_places"]


def test_overview_unknown_city_returns_404(client):
    resp = client.get("/destinations/Qzxwvutsrq/overview")
    assert resp.status_code == 404
    assert "hint" in resp.json()


def test_overview_top_places_validation(client):
    assert (
        client.get(
            "/destinations/Da Nang/overview", params={"top_places": 0}
        ).status_code
        == 422
    )
