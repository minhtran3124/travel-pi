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
