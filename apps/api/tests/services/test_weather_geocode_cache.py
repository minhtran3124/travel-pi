"""``geocode_city`` caches successful lookups process-wide; misses stay retryable and transport errors propagate before the store is touched."""

import asyncio

import pytest
from app.exceptions import WeatherUnavailableError
from app.services import weather_service

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

    first = asyncio.run(weather_service.geocode_city("Da Nang"))
    second = asyncio.run(weather_service.geocode_city("Da Nang"))

    assert first == _GEOCODE_HIT["results"][0]
    assert second == first
    assert calls["n"] == 1, "second lookup should be served from cache"


def test_cache_key_is_case_and_whitespace_insensitive(monkeypatch):
    """'Da Nang', ' da nang ' and 'DA NANG' share one cache entry."""
    fetch, calls = _counting_fetch(_GEOCODE_HIT)
    monkeypatch.setattr(weather_service, "_fetch_json", fetch)

    asyncio.run(weather_service.geocode_city("Da Nang"))
    asyncio.run(weather_service.geocode_city("  da nang  "))
    asyncio.run(weather_service.geocode_city("DA NANG"))

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
        asyncio.run(weather_service.geocode_city("Da Nang"))
    # Cache untouched → a follow-up (e.g. the node retry) tries again.
    with pytest.raises(WeatherUnavailableError):
        asyncio.run(weather_service.geocode_city("Da Nang"))
    assert calls["n"] == 2


def test_clear_geocode_cache_forces_refetch(monkeypatch):
    """clear_geocode_cache() drops entries so the next lookup fetches again."""
    fetch, calls = _counting_fetch(_GEOCODE_HIT)
    monkeypatch.setattr(weather_service, "_fetch_json", fetch)

    asyncio.run(weather_service.geocode_city("Da Nang"))
    weather_service.clear_geocode_cache()
    asyncio.run(weather_service.geocode_city("Da Nang"))

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

    asyncio.run(weather_service.geocode_city("Da Nang"))
    asyncio.run(air_quality_service.get_air_quality("Da Nang"))

    assert geocode_calls["n"] == 1
