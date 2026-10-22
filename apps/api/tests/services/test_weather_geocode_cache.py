"""``geocode_city`` caches successful lookups process-wide; misses stay retryable and transport errors propagate before the store is touched."""

import asyncio

import pytest
from app.exceptions import WeatherUnavailableError
from app.services import weather_service

_GEOCODE_HIT = {
    "results": [
        {
            "name": "Berlin",
            "country": "Germany",
            "latitude": 52.52,
            "longitude": 13.405,
        }
    ]
}
_GEOCODE_MISS = {"generationtime_ms": 0.1}  # no "results" key — city not found


def _counting_fetch(response):
    """Async ``_fetch_json`` stand-in that counts calls; returns ``response``."""
    calls = {"n": 0}

    async def _inner(url: str, params: dict) -> dict:
        calls["n"] += 1
        return response

    return _inner, calls


def test_repeat_lookup_hits_cache(monkeypatch):
    """A second lookup of the same city does not re-call Open-Meteo."""
    fetch, calls = _counting_fetch(_GEOCODE_HIT)
    monkeypatch.setattr(weather_service, "_fetch_json", fetch)

    first = asyncio.run(weather_service.geocode_city("Berlin"))
    second = asyncio.run(weather_service.geocode_city("Berlin"))

    assert first == _GEOCODE_HIT["results"][0]
    assert second == first
    assert calls["n"] == 1, "second lookup should be served from cache"


def test_cache_key_is_case_and_whitespace_insensitive(monkeypatch):
    """'Berlin', ' berlin ' and 'BERLIN' share one cache entry."""
    fetch, calls = _counting_fetch(_GEOCODE_HIT)
    monkeypatch.setattr(weather_service, "_fetch_json", fetch)

    asyncio.run(weather_service.geocode_city("Berlin"))
    asyncio.run(weather_service.geocode_city("  berlin  "))
    asyncio.run(weather_service.geocode_city("BERLIN"))

    assert calls["n"] == 1


def test_miss_is_not_cached(monkeypatch):
    """A not-found city is re-attempted every time (never cached as a hit)."""
    fetch, calls = _counting_fetch(_GEOCODE_MISS)
    monkeypatch.setattr(weather_service, "_fetch_json", fetch)

    assert asyncio.run(weather_service.geocode_city("Nowhereville")) is None
    assert asyncio.run(weather_service.geocode_city("Nowhereville")) is None
    assert calls["n"] == 2, "a miss must stay retryable, not lock in a None"


def test_transport_error_is_not_cached(monkeypatch):
    """A transient failure propagates and leaves the cache empty for a retry."""
    calls = {"n": 0}

    async def _boom(url, params):
        calls["n"] += 1
        raise WeatherUnavailableError("connection timed out")

    monkeypatch.setattr(weather_service, "_fetch_json", _boom)

    with pytest.raises(WeatherUnavailableError):
        asyncio.run(weather_service.geocode_city("Berlin"))
    # Cache untouched → a follow-up (e.g. the node retry) tries again.
    with pytest.raises(WeatherUnavailableError):
        asyncio.run(weather_service.geocode_city("Berlin"))
    assert calls["n"] == 2


def test_clear_geocode_cache_forces_refetch(monkeypatch):
    """clear_geocode_cache() drops entries so the next lookup fetches again."""
    fetch, calls = _counting_fetch(_GEOCODE_HIT)
    monkeypatch.setattr(weather_service, "_fetch_json", fetch)

    asyncio.run(weather_service.geocode_city("Berlin"))
    weather_service.clear_geocode_cache()
    asyncio.run(weather_service.geocode_city("Berlin"))

    assert calls["n"] == 2


def test_cache_is_shared_across_services(monkeypatch):
    """Air-quality reuses the coordinates weather already resolved for the city.

    ``air_quality_service.get_air_quality`` calls the same ``geocode_city``, so a
    prior weather lookup means the air-quality path never re-geocodes — the exact
    dedupe the concierge's parallel tool calls need.
    """
    from app.services import air_quality_service

    geocode_calls = {"n": 0}

    async def _fetch(url: str, params: dict) -> dict:
        if "name" in params:  # geocoding request carries the ?name= param
            geocode_calls["n"] += 1
            return _GEOCODE_HIT
        return {
            "timezone": "Asia/Ho_Chi_Minh",
            "current": {"time": "2026-06-16T14:00", "us_aqi": 42},
            "hourly": {"time": [], "us_aqi": []},
        }

    monkeypatch.setattr(weather_service, "_fetch_json", _fetch)

    asyncio.run(weather_service.geocode_city("Berlin"))
    asyncio.run(air_quality_service.get_air_quality("Berlin"))

    assert geocode_calls["n"] == 1


# ---------------------------------------------------------------------------
# Seed-preference over the network geocoder (gh-237)
# ---------------------------------------------------------------------------


def test_seeded_city_prefers_seed_coords_over_geocoder(monkeypatch):
    """A seeded city name resolves from CITIES data, not the (possibly wrong) geocoder — e.g. Open-Meteo resolves "Jeju" to a town in Ethiopia."""
    calls = {"n": 0}

    async def _wrong_country(url: str, params: dict) -> dict:
        calls["n"] += 1
        return {
            "results": [
                {
                    "name": "Jeju",
                    "country": "Ethiopia",
                    "latitude": 9.0,
                    "longitude": 38.0,
                }
            ]
        }

    monkeypatch.setattr(weather_service, "_fetch_json", _wrong_country)

    location = asyncio.run(weather_service.geocode_city("Jeju"))

    assert location is not None
    assert location["country"] == "South Korea"
    assert calls["n"] == 0, "seed match must short-circuit the network geocoder"


def test_unseeded_city_still_uses_geocoder(monkeypatch):
    """A city absent from the seed catalogue still resolves via the network geocoder."""
    fetch, calls = _counting_fetch(_GEOCODE_HIT)
    monkeypatch.setattr(weather_service, "_fetch_json", fetch)

    location = asyncio.run(weather_service.geocode_city("Berlin"))

    assert location == _GEOCODE_HIT["results"][0]
    assert calls["n"] == 1
