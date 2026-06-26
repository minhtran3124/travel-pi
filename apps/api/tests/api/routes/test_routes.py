"""Tests for GET /places/route.

Routing can make a real outbound call to OpenRouteService, so the tests that
exercise the ORS path monkeypatch ``routing_service._fetch_json`` (and the
settings, to supply an API key) — no network access in the suite. The
default path needs no key: it falls back to an offline haversine estimate.
"""

import pytest
from app.core.config import Settings
from app.core.geo import haversine_km
from app.exceptions import RoutingUnavailableError
from app.services import routing_service

# Seed place IDs (Da Nang) with known coordinates.
DRAGON_BRIDGE = "56f5b6d7-f0e2-5867-a9dd-087a98cff34c"
HAN_MARKET = "e6a5b1c9-b03f-5798-8327-e6e479e621c0"  # ~0.98 km from Dragon Bridge
MARBLE_MOUNTAINS = "26afc73a-6773-55c9-8e61-1f0fe75576e7"  # ~10.4 km from Dragon Bridge

_MODES = {"walk", "bike", "car"}


@pytest.fixture(autouse=True)
def _offline_routing(monkeypatch):
    """Keep routing tests hermetic and isolated.

    Forces the offline estimate path by default — overriding any
    ``ORS_API_KEY`` in the developer's ``.env`` so the suite never hits the
    real network — and clears the process-wide route cache so cases
    (estimate vs ORS, success vs failure) never leak into each other. Tests
    that exercise the ORS path re-override ``get_settings`` themselves.
    """
    monkeypatch.setattr(
        routing_service, "get_settings", lambda: Settings(ors_api_key=None)
    )
    routing_service.clear_route_cache()
    yield
    routing_service.clear_route_cache()


# --- Fallback (offline estimate) path -----------------------------------------


def test_route_returns_200(client):
    resp = client.get(
        "/places/route",
        params={"origin": DRAGON_BRIDGE, "destination": MARBLE_MOUNTAINS},
    )
    assert resp.status_code == 200


def test_route_response_shape(client):
    body = client.get(
        "/places/route",
        params={"origin": DRAGON_BRIDGE, "destination": MARBLE_MOUNTAINS},
    ).json()
    for field in (
        "origin",
        "destination",
        "straight_line_km",
        "recommended_mode",
        "legs",
        "source",
        "attribution",
    ):
        assert field in body
    assert body["origin"]["kind"] == "place"
    assert body["origin"]["id"] == DRAGON_BRIDGE
    assert body["destination"]["id"] == MARBLE_MOUNTAINS


def test_route_without_api_key_uses_estimate(client):
    body = client.get(
        "/places/route",
        params={"origin": DRAGON_BRIDGE, "destination": MARBLE_MOUNTAINS},
    ).json()
    assert body["source"] == "estimate"
    assert "estimate" in body["attribution"].lower()


def test_route_has_one_leg_per_mode(client):
    body = client.get(
        "/places/route",
        params={"origin": DRAGON_BRIDGE, "destination": MARBLE_MOUNTAINS},
    ).json()
    assert {leg["mode"] for leg in body["legs"]} == _MODES
    for leg in body["legs"]:
        assert leg["distance_km"] > 0
        assert leg["duration_minutes"] > 0


def test_route_far_pair_recommends_car(client):
    body = client.get(
        "/places/route",
        params={"origin": DRAGON_BRIDGE, "destination": MARBLE_MOUNTAINS},
    ).json()
    assert body["recommended_mode"] == "car"
    # ~10.4 km straight line between the two.
    assert 9 < body["straight_line_km"] < 12


def test_route_close_pair_recommends_walk(client):
    body = client.get(
        "/places/route",
        params={"origin": DRAGON_BRIDGE, "destination": HAN_MARKET},
    ).json()
    assert body["recommended_mode"] == "walk"
    assert body["straight_line_km"] < 1.5


def test_route_estimate_walk_is_slower_than_car(client):
    """Same distance, but the per-mode durations differ by speed."""
    body = client.get(
        "/places/route",
        params={"origin": DRAGON_BRIDGE, "destination": MARBLE_MOUNTAINS},
    ).json()
    legs = {leg["mode"]: leg for leg in body["legs"]}
    assert legs["walk"]["duration_minutes"] > legs["bike"]["duration_minutes"]
    assert legs["bike"]["duration_minutes"] > legs["car"]["duration_minutes"]


# --- Not found ----------------------------------------------------------------


def test_route_unknown_origin_returns_404(client):
    resp = client.get(
        "/places/route",
        params={"origin": "no-such-id", "destination": MARBLE_MOUNTAINS},
    )
    assert resp.status_code == 404


def test_route_unknown_destination_returns_404(client):
    resp = client.get(
        "/places/route",
        params={"origin": DRAGON_BRIDGE, "destination": "no-such-id"},
    )
    assert resp.status_code == 404


def test_route_missing_params_returns_422(client):
    assert client.get("/places/route").status_code == 422
    assert (
        client.get("/places/route", params={"origin": DRAGON_BRIDGE}).status_code == 422
    )


# --- OpenRouteService path (monkeypatched) ------------------------------------


@pytest.fixture()
def with_ors(monkeypatch):
    """Enable the ORS provider with a fake key and a canned directions reply."""
    monkeypatch.setattr(
        routing_service,
        "get_settings",
        lambda: Settings(ors_api_key="test-key"),
    )

    async def _fake_fetch(url: str, params: dict) -> dict:
        # ORS GET /v2/directions/{profile} returns GeoJSON; the profile is in
        # the URL, so vary the numbers a little per profile for realism.
        profile = url.rsplit("/", 1)[-1]
        distance_m = {"foot-walking": 2500.0}.get(profile, 3000.0)
        duration_s = {
            "foot-walking": 1800.0,
            "cycling-regular": 600.0,
            "driving-car": 300.0,
        }.get(profile, 600.0)
        return {
            "features": [
                {"properties": {"summary": {"distance": distance_m, "duration": duration_s}}}
            ]
        }

    monkeypatch.setattr(routing_service, "_fetch_json", _fake_fetch)


def test_route_with_ors_uses_provider(client, with_ors):
    body = client.get(
        "/places/route",
        params={"origin": DRAGON_BRIDGE, "destination": MARBLE_MOUNTAINS},
    ).json()
    assert body["source"] == "openrouteservice"
    assert "openrouteservice" in body["attribution"].lower()


def test_route_with_ors_parses_distance_and_duration(client, with_ors):
    body = client.get(
        "/places/route",
        params={"origin": DRAGON_BRIDGE, "destination": MARBLE_MOUNTAINS},
    ).json()
    legs = {leg["mode"]: leg for leg in body["legs"]}
    # foot-walking: 2500 m / 1800 s -> 2.5 km / 30 min
    assert legs["walk"]["distance_km"] == 2.5
    assert legs["walk"]["duration_minutes"] == 30.0
    # driving-car: 3000 m / 300 s -> 3.0 km / 5 min
    assert legs["car"]["distance_km"] == 3.0
    assert legs["car"]["duration_minutes"] == 5.0


def test_route_ors_upstream_failure_falls_back_to_estimate(client, monkeypatch):
    """When every ORS leg fails (e.g. upstream is down), the route still
    returns a usable response built from the offline estimate — the
    ``source`` field flips to ``"estimate"`` so callers can tell."""
    monkeypatch.setattr(
        routing_service,
        "get_settings",
        lambda: Settings(ors_api_key="test-key"),
    )

    async def _boom(url, params):
        raise RoutingUnavailableError("connection timed out")

    monkeypatch.setattr(routing_service, "_fetch_json", _boom)
    resp = client.get(
        "/places/route",
        params={"origin": DRAGON_BRIDGE, "destination": MARBLE_MOUNTAINS},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "estimate"
    assert {leg["mode"] for leg in body["legs"]} == {"walk", "bike", "car"}


def test_route_ors_unexpected_response_falls_back_to_estimate(client, monkeypatch):
    """An empty/malformed ORS payload is treated the same as upstream
    failure — fall back per-leg rather than surfacing a 502."""
    monkeypatch.setattr(
        routing_service,
        "get_settings",
        lambda: Settings(ors_api_key="test-key"),
    )

    async def _empty(url, params):
        return {}  # no "features" key

    monkeypatch.setattr(routing_service, "_fetch_json", _empty)
    resp = client.get(
        "/places/route",
        params={"origin": DRAGON_BRIDGE, "destination": MARBLE_MOUNTAINS},
    )
    assert resp.status_code == 200
    assert resp.json()["source"] == "estimate"


# --- Unit: recommend_mode + haversine -----------------------------------------


def test_recommend_mode_thresholds():
    assert routing_service.recommend_mode(0.5) == "walk"
    assert routing_service.recommend_mode(1.5) == "walk"
    assert routing_service.recommend_mode(3.0) == "bike"
    assert routing_service.recommend_mode(8.0) == "bike"
    assert routing_service.recommend_mode(8.1) == "car"
    assert routing_service.recommend_mode(50.0) == "car"


def test_haversine_known_distance():
    # Dragon Bridge -> Marble Mountains is ~10.4 km.
    km = haversine_km(16.0607, 108.2275, 15.9736, 108.2625)
    assert 9 < km < 12


def test_haversine_zero_for_same_point():
    assert haversine_km(16.0, 108.0, 16.0, 108.0) == pytest.approx(0.0)


# --- City-to-city routing -----------------------------------------------------


def test_city_route_returns_200(client):
    resp = client.get(
        "/cities/route", params={"origin": "Da Nang", "destination": "Hanoi"}
    )
    assert resp.status_code == 200


def test_city_route_response_shape(client):
    body = client.get(
        "/cities/route", params={"origin": "Da Nang", "destination": "Hanoi"}
    ).json()
    assert body["origin"]["kind"] == "city"
    assert body["origin"]["id"] == "Da Nang"
    assert body["destination"]["id"] == "Hanoi"
    assert {leg["mode"] for leg in body["legs"]} == _MODES
    assert body["recommended_mode"] == "car"  # different cities are always far


def test_city_route_is_case_insensitive(client):
    body = client.get(
        "/cities/route", params={"origin": "da nang", "destination": "HANOI"}
    ).json()
    assert body["origin"]["id"] == "Da Nang"
    assert body["destination"]["id"] == "Hanoi"


def test_city_route_is_fuzzy_tolerant(client):
    """Misspellings / dropped spaces still resolve (e.g. 'danang')."""
    body = client.get(
        "/cities/route", params={"origin": "danang", "destination": "ha noi"}
    ).json()
    assert body["origin"]["id"] == "Da Nang"
    assert body["destination"]["id"] == "Hanoi"


def test_city_route_unknown_origin_returns_404(client):
    resp = client.get(
        "/cities/route", params={"origin": "Nowhereville", "destination": "Hanoi"}
    )
    assert resp.status_code == 404


def test_city_route_missing_params_returns_422(client):
    assert client.get("/cities/route").status_code == 422


# --- Cache --------------------------------------------------------------------


def test_route_result_is_cached(client, monkeypatch):
    """A second identical ORS route is served from cache — no second fetch."""
    monkeypatch.setattr(
        routing_service, "get_settings", lambda: Settings(ors_api_key="test-key")
    )
    calls = {"n": 0}

    async def _counting_fetch(url, params):
        calls["n"] += 1
        return {
            "features": [
                {"properties": {"summary": {"distance": 1000.0, "duration": 600.0}}}
            ]
        }

    monkeypatch.setattr(routing_service, "_fetch_json", _counting_fetch)

    params = {"origin": DRAGON_BRIDGE, "destination": MARBLE_MOUNTAINS}
    client.get("/places/route", params=params)
    after_first = calls["n"]
    assert after_first == 3  # one fetch per travel mode
    client.get("/places/route", params=params)
    assert calls["n"] == after_first  # cache hit — no extra fetches
