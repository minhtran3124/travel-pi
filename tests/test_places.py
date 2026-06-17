"""Tests for the /places endpoints."""

import pytest
from app.services import place_service
from fastapi.testclient import TestClient

# ── List all (paginated) ──────────────────────────────────────────────────────


def test_list_places_status(client: TestClient) -> None:
    assert client.get("/places").status_code == 200


def test_list_places_returns_paginated_envelope(client: TestClient) -> None:
    data = client.get("/places").json()
    for field in ("total", "limit", "offset", "results"):
        assert field in data
    assert isinstance(data["results"], list)
    assert data["total"] > 0


def test_list_places_fields(client: TestClient) -> None:
    place = client.get("/places").json()["results"][0]
    for field in (
        "id",
        "name",
        "city",
        "country",
        "category",
        "description",
        "address",
        "rating",
        "review_count",
        "price_level",
        "image_url",
        "tags",
        "is_recommended",
    ):
        assert field in place, f"missing field: {field}"


def test_list_places_rating_range(client: TestClient) -> None:
    for p in client.get("/places", params={"limit": 100}).json()["results"]:
        assert 0 <= p["rating"] <= 5


def test_list_places_price_level_range(client: TestClient) -> None:
    for p in client.get("/places", params={"limit": 100}).json()["results"]:
        assert 1 <= p["price_level"] <= 4


def test_list_places_category_valid(client: TestClient) -> None:
    valid = {"attraction", "restaurant", "cafe", "activity", "nightlife", "shopping"}
    for p in client.get("/places", params={"limit": 100}).json()["results"]:
        assert p["category"] in valid, f"unexpected category: {p['category']}"


def test_list_places_default_limit(client: TestClient) -> None:
    body = client.get("/places").json()
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert len(body["results"]) <= 20


def test_list_places_custom_limit(client: TestClient) -> None:
    body = client.get("/places", params={"limit": 5}).json()
    assert body["limit"] == 5
    assert len(body["results"]) <= 5


def test_list_places_offset_shifts_page(client: TestClient) -> None:
    all_ids = [
        p["id"] for p in client.get("/places", params={"limit": 100}).json()["results"]
    ]
    page1 = client.get("/places", params={"limit": 3, "offset": 0}).json()["results"]
    page2 = client.get("/places", params={"limit": 3, "offset": 3}).json()["results"]
    assert [p["id"] for p in page1] == all_ids[:3]
    assert [p["id"] for p in page2] == all_ids[3:6]


def test_list_places_total_stable_across_pages(client: TestClient) -> None:
    t1 = client.get("/places", params={"limit": 5, "offset": 0}).json()["total"]
    t2 = client.get("/places", params={"limit": 5, "offset": 20}).json()["total"]
    assert t1 == t2


def test_list_places_limit_validation(client: TestClient) -> None:
    assert client.get("/places", params={"limit": 0}).status_code == 422
    assert client.get("/places", params={"limit": 501}).status_code == 422


def test_list_places_offset_validation(client: TestClient) -> None:
    assert client.get("/places", params={"offset": -1}).status_code == 422


# ── Cities endpoint ───────────────────────────────────────────────────────────


def test_cities_status(client: TestClient) -> None:
    assert client.get("/places/cities").status_code == 200


def test_cities_is_sorted_list(client: TestClient) -> None:
    cities = client.get("/places/cities").json()
    assert isinstance(cities, list)
    assert cities == sorted(cities)


def test_cities_non_empty(client: TestClient) -> None:
    assert len(client.get("/places/cities").json()) > 0


# ── Categories endpoint ───────────────────────────────────────────────────────


def test_categories_status(client: TestClient) -> None:
    assert client.get("/places/categories").status_code == 200


def test_categories_is_sorted_list(client: TestClient) -> None:
    cats = client.get("/places/categories").json()
    assert isinstance(cats, list)
    assert cats == sorted(cats)


# ── Search (paginated) ────────────────────────────────────────────────────────


def test_search_status(client: TestClient) -> None:
    assert client.get("/places/search").status_code == 200


def test_search_response_structure(client: TestClient) -> None:
    data = client.get("/places/search").json()
    for field in ("total", "limit", "offset", "results"):
        assert field in data
    assert isinstance(data["results"], list)
    assert data["total"] >= len(data["results"])


def test_search_by_city(client: TestClient) -> None:
    data = client.get("/places/search", params={"city": "Hanoi", "limit": 100}).json()
    assert data["total"] > 0
    for place in data["results"]:
        assert place["city"] == "Hanoi"


def test_search_city_case_insensitive(client: TestClient) -> None:
    lower = client.get("/places/search", params={"city": "hanoi"}).json()
    upper = client.get("/places/search", params={"city": "HANOI"}).json()
    assert lower["total"] == upper["total"]


def test_search_unknown_city_returns_empty(client: TestClient) -> None:
    resp = client.get("/places/search", params={"city": "Atlantis"})
    data = resp.json()
    assert resp.status_code == 200
    assert data["total"] == 0
    assert data["results"] == []


def test_search_by_category(client: TestClient) -> None:
    data = client.get(
        "/places/search", params={"category": "restaurant", "limit": 100}
    ).json()
    assert data["total"] > 0
    for place in data["results"]:
        assert place["category"] == "restaurant"


def test_search_invalid_category_422(client: TestClient) -> None:
    assert (
        client.get("/places/search", params={"category": "invalid_cat"}).status_code
        == 422
    )


def test_search_by_min_rating(client: TestClient) -> None:
    data = client.get("/places/search", params={"min_rating": 4.5, "limit": 100}).json()
    assert data["total"] > 0
    for place in data["results"]:
        assert place["rating"] >= 4.5


def test_search_by_price_level(client: TestClient) -> None:
    data = client.get("/places/search", params={"price_level": 1, "limit": 100}).json()
    assert data["total"] > 0
    for place in data["results"]:
        assert place["price_level"] == 1


def test_search_recommended_only(client: TestClient) -> None:
    data = client.get(
        "/places/search", params={"recommended": True, "limit": 100}
    ).json()
    assert data["total"] > 0
    for place in data["results"]:
        assert place["is_recommended"] is True


def test_search_combined_filters(client: TestClient) -> None:
    data = client.get(
        "/places/search",
        params={"city": "Da Nang", "category": "attraction", "limit": 100},
    ).json()
    assert data["total"] > 0
    for place in data["results"]:
        assert place["city"] == "Da Nang"
        assert place["category"] == "attraction"


def test_search_echoes_params(client: TestClient) -> None:
    data = client.get(
        "/places/search", params={"city": "Hanoi", "category": "cafe"}
    ).json()
    assert data["city"] == "Hanoi"
    assert data["category"] == "cafe"


def test_search_sort_rating_desc(client: TestClient) -> None:
    results = client.get("/places/search", params={"sort": "rating_desc"}).json()[
        "results"
    ]
    ratings = [p["rating"] for p in results]
    assert ratings == sorted(ratings, reverse=True)


def test_search_sort_rating_asc(client: TestClient) -> None:
    results = client.get("/places/search", params={"sort": "rating_asc"}).json()[
        "results"
    ]
    ratings = [p["rating"] for p in results]
    assert ratings == sorted(ratings)


def test_search_sort_name(client: TestClient) -> None:
    results = client.get("/places/search", params={"sort": "name"}).json()["results"]
    names = [p["name"].lower() for p in results]
    assert names == sorted(names)


def test_search_sort_price_asc(client: TestClient) -> None:
    results = client.get("/places/search", params={"sort": "price_asc"}).json()[
        "results"
    ]
    levels = [p["price_level"] for p in results]
    assert levels == sorted(levels)


def test_search_invalid_sort_returns_422(client: TestClient) -> None:
    """``sort`` is a PlaceSort enum — an unknown value is now 422 instead of
    being silently coerced to the default."""
    resp = client.get("/places/search", params={"sort": "bogus"})
    assert resp.status_code == 422


def test_search_empty_string_min_rating_treated_as_no_filter(
    client: TestClient,
) -> None:
    resp = client.get("/places/search", params={"min_rating": ""})
    assert resp.status_code == 200
    assert resp.json()["min_rating"] is None


def test_search_empty_string_price_level_treated_as_no_filter(
    client: TestClient,
) -> None:
    resp = client.get("/places/search", params={"price_level": ""})
    assert resp.status_code == 200
    assert resp.json()["price_level"] is None


def test_search_all_empty_strings(client: TestClient) -> None:
    """Empty strings on the free-text + numeric params are treated as no filter.
    ``category`` is now a strict enum, so it is excluded from this test —
    sending ``category=""`` correctly 422s (covered separately)."""
    resp = client.get(
        "/places/search", params={"city": "", "min_rating": "", "price_level": ""}
    )
    assert resp.status_code == 200
    assert resp.json()["total"] > 0


def test_search_empty_string_category_returns_422(client: TestClient) -> None:
    """``category`` is an enum: an empty string is not a valid value."""
    assert client.get("/places/search", params={"category": ""}).status_code == 422


def test_search_pagination(client: TestClient) -> None:
    total = client.get("/places/search", params={"city": "Da Nang"}).json()["total"]
    if total > 1:
        p1 = client.get(
            "/places/search", params={"city": "Da Nang", "limit": 1, "offset": 0}
        ).json()
        p2 = client.get(
            "/places/search", params={"city": "Da Nang", "limit": 1, "offset": 1}
        ).json()
        assert p1["total"] == total
        assert p2["total"] == total
        assert p1["results"][0]["id"] != p2["results"][0]["id"]


# ── Detail ────────────────────────────────────────────────────────────────────


def _first_place_id(client: TestClient) -> str:
    return client.get("/places").json()["results"][0]["id"]


def test_get_place_status(client: TestClient) -> None:
    assert client.get(f"/places/{_first_place_id(client)}").status_code == 200


def test_get_place_correct_id(client: TestClient) -> None:
    pid = _first_place_id(client)
    assert client.get(f"/places/{pid}").json()["id"] == pid


def test_get_place_not_found(client: TestClient) -> None:
    assert client.get("/places/nonexistent-id").status_code == 404


# ---------------------------------------------------------------------------
# GET /places/nearby
# ---------------------------------------------------------------------------

_DRAGON_BRIDGE = "56f5b6d7-f0e2-5867-a9dd-087a98cff34c"  # Da Nang


def test_nearby_returns_200(client: TestClient) -> None:
    resp = client.get("/places/nearby", params={"place_id": _DRAGON_BRIDGE})
    assert resp.status_code == 200


def test_nearby_response_shape(client: TestClient) -> None:
    body = client.get(
        "/places/nearby", params={"place_id": _DRAGON_BRIDGE, "radius_km": 3}
    ).json()
    for field in ("origin_place_id", "radius_km", "count", "results"):
        assert field in body
    assert body["origin_place_id"] == _DRAGON_BRIDGE
    assert body["count"] == len(body["results"])


def test_nearby_excludes_origin_and_sorts_by_distance(client: TestClient) -> None:
    body = client.get(
        "/places/nearby", params={"place_id": _DRAGON_BRIDGE, "radius_km": 5}
    ).json()
    ids = [p["id"] for p in body["results"]]
    assert _DRAGON_BRIDGE not in ids  # origin excluded
    distances = [p["distance_km"] for p in body["results"]]
    assert distances == sorted(distances)  # nearest-first
    for p in body["results"]:
        assert p["distance_km"] <= 5


def test_nearby_respects_limit(client: TestClient) -> None:
    body = client.get(
        "/places/nearby",
        params={"place_id": _DRAGON_BRIDGE, "radius_km": 50, "limit": 2},
    ).json()
    assert len(body["results"]) <= 2


def test_nearby_tiny_radius_returns_empty(client: TestClient) -> None:
    body = client.get(
        "/places/nearby", params={"place_id": _DRAGON_BRIDGE, "radius_km": 0.01}
    ).json()
    assert body["results"] == []
    assert body["count"] == 0


def test_nearby_category_filter(client: TestClient) -> None:
    body = client.get(
        "/places/nearby",
        params={"place_id": _DRAGON_BRIDGE, "radius_km": 50, "category": "restaurant"},
    ).json()
    assert all(p["category"] == "restaurant" for p in body["results"])


def test_nearby_invalid_category_returns_422(client: TestClient) -> None:
    resp = client.get(
        "/places/nearby",
        params={"place_id": _DRAGON_BRIDGE, "category": "spaceship"},
    )
    assert resp.status_code == 422


def test_nearby_unknown_place_returns_404(client: TestClient) -> None:
    resp = client.get("/places/nearby", params={"place_id": "no-such-id"})
    assert resp.status_code == 404


def test_nearby_radius_validation(client: TestClient) -> None:
    assert (
        client.get(
            "/places/nearby", params={"place_id": _DRAGON_BRIDGE, "radius_km": 0}
        ).status_code
        == 422
    )
    assert (
        client.get(
            "/places/nearby", params={"place_id": _DRAGON_BRIDGE, "radius_km": 999}
        ).status_code
        == 422
    )


# ---------------------------------------------------------------------------
# GET /places/search — fuzzy city matching
# ---------------------------------------------------------------------------


def test_search_places_city_is_fuzzy(client: TestClient) -> None:
    body = client.get("/places/search", params={"city": "danang"}).json()
    assert body["total"] > 0
    assert body["city"] == "Da Nang"  # echoes the resolved name
    assert all(p["city"] == "Da Nang" for p in body["results"])


def test_search_places_unknown_city_returns_zero(client: TestClient) -> None:
    body = client.get("/places/search", params={"city": "zzzznowhere"}).json()
    assert body["total"] == 0


# ── Bad numeric input via the shared params helper ────────────────────────────


def test_search_min_rating_non_numeric_returns_422(client: TestClient) -> None:
    resp = client.get("/places/search", params={"min_rating": "abc"})
    assert resp.status_code == 422
    assert "Min" in resp.json()["message"] or "min_rating" in resp.json()["message"]


def test_search_min_rating_out_of_range_returns_422(client: TestClient) -> None:
    assert client.get("/places/search", params={"min_rating": "9"}).status_code == 422


def test_search_price_level_out_of_range_returns_422(client: TestClient) -> None:
    assert client.get("/places/search", params={"price_level": "7"}).status_code == 422


def test_dashboard_places_bad_min_rating_returns_200_with_error(
    client: TestClient,
) -> None:
    """Dashboard renders a friendly inline error rather than 500'ing."""
    resp = client.get("/dashboard/places", params={"min_rating": "abc"})
    assert resp.status_code == 200
    assert "Min rating" in resp.text


# ---------------------------------------------------------------------------
# Short codes (PLC-XXXXXX)
# ---------------------------------------------------------------------------


def test_place_response_exposes_short_code(client: TestClient) -> None:
    body = client.get(f"/places/{_DRAGON_BRIDGE}").json()
    assert body.get("short_code", "").startswith("PLC-")
    assert len(body["short_code"]) == 10


def test_get_place_by_short_code(client: TestClient) -> None:
    short_code = client.get(f"/places/{_DRAGON_BRIDGE}").json()["short_code"]
    body = client.get(f"/places/{short_code}").json()
    assert body["id"] == _DRAGON_BRIDGE


def test_get_place_by_lowercased_short_code(client: TestClient) -> None:
    short_code = client.get(f"/places/{_DRAGON_BRIDGE}").json()["short_code"]
    body = client.get(f"/places/{short_code.lower()}").json()
    assert body["id"] == _DRAGON_BRIDGE


def test_nearby_accepts_short_code(client: TestClient) -> None:
    short_code = client.get(f"/places/{_DRAGON_BRIDGE}").json()["short_code"]
    resp = client.get("/places/nearby", params={"place_id": short_code})
    assert resp.status_code == 200


# ── NL query parsing (service-level) ──────────────────────────────────────────


@pytest.mark.parametrize(
    "query, field, expected",
    [
        ("romantic dinner in Hanoi under $40", "city", "Hanoi"),
        ("romantic dinner in Hanoi under $40", "category", "restaurant"),
        ("romantic dinner in Hanoi under $40", "price_level", 2),
        ("cheap coffee in Da Nang", "category", "cafe"),
        ("cheap coffee in Da Nang", "price_level", 1),
        ("cheap coffee in Da Nang", "city", "Da Nang"),
        ("best museums to visit", "category", "attraction"),
        ("best museums to visit", "min_rating", 4.5),
        ("4 star hotels", "min_rating", 4.0),
        ("10 star hotels", "min_rating", 5.0),  # multi-digit captured whole, clamped
        ("luxury shopping", "price_level", 4),
        ("luxury shopping", "category", "shopping"),
        ("nothing useful here", "city", None),
        ("nothing useful here", "category", None),
        ("nothing useful here", "price_level", None),
        ("nothing useful here", "min_rating", None),
    ],
)
def test_parse_nl_query(query, field, expected) -> None:
    parsed = place_service.parse_nl_query(query)
    assert getattr(parsed, field) == expected


# ── NL search endpoint (HTTP) ─────────────────────────────────────────────────


def test_nl_search_status(client: TestClient) -> None:
    resp = client.post("/places/search/nl", json={"query": "dinner in Hanoi"})
    assert resp.status_code == 200


def test_nl_search_echoes_parsed_filters(client: TestClient) -> None:
    body = client.post(
        "/places/search/nl",
        json={"query": "romantic dinner in Hanoi under $40"},
    ).json()
    assert body["query"] == "romantic dinner in Hanoi under $40"
    assert body["parsed"] == {
        "city": "Hanoi",
        "category": "restaurant",
        "min_rating": None,
        "price_level": 2,
    }


def test_nl_search_results_match_parsed_filters(client: TestClient) -> None:
    body = client.post(
        "/places/search/nl",
        json={"query": "romantic dinner in Hanoi under $40"},
    ).json()
    assert body["total"] >= 1
    for place in body["results"]:
        assert place["city"] == "Hanoi"
        assert place["category"] == "restaurant"
        assert place["price_level"] == 2


def test_nl_search_empty_query_422(client: TestClient) -> None:
    assert client.post("/places/search/nl", json={"query": ""}).status_code == 422


def test_nl_search_missing_query_422(client: TestClient) -> None:
    assert client.post("/places/search/nl", json={}).status_code == 422


def test_nl_search_no_signal_returns_all_with_null_parsed(client: TestClient) -> None:
    body = client.post("/places/search/nl", json={"query": "show me stuff"}).json()
    assert body["parsed"] == {
        "city": None,
        "category": None,
        "min_rating": None,
        "price_level": None,
    }
    assert body["total"] > 0


def test_nl_search_pagination(client: TestClient) -> None:
    body = client.post(
        "/places/search/nl?limit=2",
        json={"query": "show me stuff"},
    ).json()
    assert body["limit"] == 2
    assert len(body["results"]) <= 2
