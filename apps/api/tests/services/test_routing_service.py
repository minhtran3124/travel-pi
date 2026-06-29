"""RoutingService geometry capture (specs/agent-side-panel Task 1.0).

The road polyline ORS already returns in the directions response is now kept on
``RouteResponse.geometry`` (recommended-mode line) for the map side-panel. These
tests drive ``get_route_between`` with hand-built endpoints (no DB) and stub the
ORS HTTP call, covering both the real-routing path (geometry populated) and the
offline estimate path (geometry None).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import app.services.routing_service as rs
import pytest
from app.exceptions import NotFoundError
from app.schemas.route import RouteEndpoint

_ORS_RESPONSE = {
    "features": [
        {
            "properties": {"summary": {"distance": 11500.0, "duration": 720.0}},
            "geometry": {
                "coordinates": [[108.22, 16.06], [108.225, 16.058], [108.23, 16.06]]
            },
        }
    ]
}


def _endpoints() -> tuple[RouteEndpoint, RouteEndpoint]:
    origin = RouteEndpoint(
        kind="place", id="PLC-A", name="Hotel", latitude=16.06, longitude=108.22
    )
    dest = RouteEndpoint(
        kind="place", id="PLC-B", name="Dragon Bridge", latitude=16.06, longitude=108.23
    )
    return origin, dest


def _settings(*, provider: bool) -> SimpleNamespace:
    return SimpleNamespace(
        routing_provider_enabled=provider,
        ors_api_key="test-key" if provider else None,
        ors_base_url="https://api.openrouteservice.org",
        ors_timeout_seconds=5,
    )


def test_geometry_populated_from_ors(monkeypatch):
    rs.clear_route_cache()
    monkeypatch.setattr(rs, "get_settings", lambda: _settings(provider=True))

    async def _fake_fetch(url, params):
        return _ORS_RESPONSE

    monkeypatch.setattr(rs, "_fetch_json", _fake_fetch)

    origin, dest = _endpoints()
    out = asyncio.run(rs.RoutingService(None).get_route_between(origin, dest))

    assert out.source == "openrouteservice"
    assert out.geometry == [[108.22, 16.06], [108.225, 16.058], [108.23, 16.06]]


def test_geometry_none_in_estimate_mode(monkeypatch):
    rs.clear_route_cache()
    monkeypatch.setattr(rs, "get_settings", lambda: _settings(provider=False))

    origin, dest = _endpoints()
    out = asyncio.run(rs.RoutingService(None).get_route_between(origin, dest))

    assert out.source == "estimate"
    assert out.geometry is None


def _service_with_cities(names, *, coords=None):
    """A RoutingService whose city repo is a stub (no DB)."""
    svc = rs.RoutingService(None)
    svc._city = SimpleNamespace(
        distinct_names=lambda: names,
        get=lambda n: (
            SimpleNamespace(name=n, latitude=coords[0], longitude=coords[1])
            if coords is not None
            else None
        ),
    )
    return svc


def test_city_endpoint_prefers_seed_without_geocoding(monkeypatch):
    """A seeded city resolves offline; the geocoder is never called."""
    called = {"geo": False}

    async def _geo(_city):
        called["geo"] = True
        return None

    monkeypatch.setattr(rs, "geocode_city", _geo)
    svc = _service_with_cities(["Da Nang"], coords=(16.07, 108.22))

    ep = asyncio.run(svc._city_endpoint("danang", "Origin"))

    assert (ep.name, ep.latitude, ep.longitude) == ("Da Nang", 16.07, 108.22)
    assert called["geo"] is False


def test_city_endpoint_falls_back_to_geocoder(monkeypatch):
    """A name the ASCII seed cannot place (e.g. "Hà Nội") resolves via Open-Meteo."""

    async def _geo(city):
        assert city == "Hà Nội"
        return {"name": "Hà Nội", "latitude": 21.0245, "longitude": 105.8412}

    monkeypatch.setattr(rs, "geocode_city", _geo)
    svc = _service_with_cities(["Da Nang"])  # seed miss -> geocode fallback

    ep = asyncio.run(svc._city_endpoint("Hà Nội", "Origin"))

    assert ep.name == "Hà Nội"
    assert (ep.latitude, ep.longitude) == (21.0245, 105.8412)


def test_city_endpoint_not_found_when_geocoder_empty(monkeypatch):
    """Neither seed nor geocoder resolves the name -> NotFoundError."""

    async def _geo(_city):
        return None

    monkeypatch.setattr(rs, "geocode_city", _geo)
    svc = _service_with_cities(["Da Nang"])

    with pytest.raises(NotFoundError):
        asyncio.run(svc._city_endpoint("Nowhere-Xyzzy", "Origin"))
