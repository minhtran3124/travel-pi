"""Tests for hotel endpoints: list, search, detail, and booking."""

import pytest

from tests.conftest import VALID_CHECK_IN, VALID_CHECK_OUT, get_first_hotel_id


# ---------------------------------------------------------------------------
# GET /hotels  (paginated)
# ---------------------------------------------------------------------------


def test_list_hotels_returns_200(client):
    resp = client.get("/hotels")
    assert resp.status_code == 200


def test_list_hotels_returns_paginated_envelope(client):
    body = client.get("/hotels").json()
    for field in ("total", "limit", "offset", "results"):
        assert field in body
    assert isinstance(body["results"], list)
    assert body["total"] > 0


def test_list_hotels_item_has_required_fields(client):
    hotel = client.get("/hotels").json()["results"][0]
    for field in (
        "id", "name", "city", "country", "address",
        "star_rating", "price_per_night", "currency",
        "amenities", "rating", "review_count",
    ):
        assert field in hotel


def test_list_hotels_country_is_non_empty(client):
    for h in client.get("/hotels", params={"limit": 500}).json()["results"]:
        assert h["country"], f"hotel {h['id']} has no country"


def test_list_hotels_country_matches_city(client):
    """Each hotel's country must agree with its city's country in cities.py."""
    from app.data.cities import CITIES

    country_by_city = {c["name"]: c["country"] for c in CITIES}
    for h in client.get("/hotels", params={"limit": 500}).json()["results"]:
        assert h["country"] == country_by_city[h["city"]]


def test_get_hotel_includes_country(client):
    hotel_id = client.get("/hotels").json()["results"][0]["id"]
    assert client.get(f"/hotels/{hotel_id}").json()["country"]


def test_list_hotels_star_rating_in_range(client):
    for h in client.get("/hotels", params={"limit": 500}).json()["results"]:
        assert 1 <= h["star_rating"] <= 5


def test_list_hotels_price_is_positive(client):
    for h in client.get("/hotels", params={"limit": 500}).json()["results"]:
        assert h["price_per_night"] > 0


# Pagination behaviour
def test_list_hotels_default_limit(client):
    body = client.get("/hotels").json()
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert len(body["results"]) <= 20


def test_list_hotels_custom_limit(client):
    body = client.get("/hotels", params={"limit": 5}).json()
    assert body["limit"] == 5
    assert len(body["results"]) <= 5


def test_list_hotels_offset_shifts_page(client):
    all_ids = [h["id"] for h in client.get("/hotels", params={"limit": 500}).json()["results"]]
    page1 = client.get("/hotels", params={"limit": 3, "offset": 0}).json()["results"]
    page2 = client.get("/hotels", params={"limit": 3, "offset": 3}).json()["results"]
    assert [h["id"] for h in page1] == all_ids[:3]
    assert [h["id"] for h in page2] == all_ids[3:6]


def test_list_hotels_total_stable_across_pages(client):
    t1 = client.get("/hotels", params={"limit": 5, "offset": 0}).json()["total"]
    t2 = client.get("/hotels", params={"limit": 5, "offset": 10}).json()["total"]
    assert t1 == t2


def test_list_hotels_offset_beyond_total_returns_empty(client):
    total = client.get("/hotels").json()["total"]
    body = client.get("/hotels", params={"offset": total + 100}).json()
    assert body["results"] == []
    assert body["total"] == total


def test_list_hotels_limit_validation(client):
    assert client.get("/hotels", params={"limit": 0}).status_code == 422
    assert client.get("/hotels", params={"limit": 501}).status_code == 422


def test_list_hotels_offset_validation(client):
    assert client.get("/hotels", params={"offset": -1}).status_code == 422


# ---------------------------------------------------------------------------
# GET /hotels/search
# ---------------------------------------------------------------------------


def test_search_hotels_returns_200(client):
    resp = client.get(
        "/hotels/search",
        params={"city": "Da Nang", "check_in": VALID_CHECK_IN, "check_out": VALID_CHECK_OUT},
    )
    assert resp.status_code == 200


def test_search_hotels_response_structure(client):
    body = client.get(
        "/hotels/search",
        params={"city": "Da Nang", "check_in": VALID_CHECK_IN, "check_out": VALID_CHECK_OUT},
    ).json()
    for field in ("total", "limit", "offset", "search", "results"):
        assert field in body


def test_search_hotels_results_include_country(client):
    data = client.get(
        "/hotels/search",
        params={"city": "Da Nang", "check_in": VALID_CHECK_IN, "check_out": VALID_CHECK_OUT},
    ).json()
    assert data["total"] > 0
    for h in data["results"]:
        assert h["country"] == "Vietnam"


def test_search_hotels_total_gte_results(client):
    body = client.get(
        "/hotels/search",
        params={"city": "Da Nang", "check_in": VALID_CHECK_IN, "check_out": VALID_CHECK_OUT},
    ).json()
    assert body["total"] >= len(body["results"])


def test_search_hotels_returns_matching_city(client):
    results = client.get(
        "/hotels/search",
        params={"city": "Da Nang", "check_in": VALID_CHECK_IN, "check_out": VALID_CHECK_OUT},
    ).json()["results"]
    assert len(results) > 0
    for hotel in results:
        assert hotel["city"].lower() == "da nang"


def test_search_hotels_case_insensitive(client):
    upper = client.get(
        "/hotels/search",
        params={"city": "DA NANG", "check_in": VALID_CHECK_IN, "check_out": VALID_CHECK_OUT},
    ).json()
    lower = client.get(
        "/hotels/search",
        params={"city": "da nang", "check_in": VALID_CHECK_IN, "check_out": VALID_CHECK_OUT},
    ).json()
    assert upper["total"] == lower["total"]


def test_search_hotels_unknown_city_returns_zero(client):
    body = client.get(
        "/hotels/search",
        params={"city": "Atlantis", "check_in": VALID_CHECK_IN, "check_out": VALID_CHECK_OUT},
    ).json()
    assert body["total"] == 0
    assert body["results"] == []


def test_search_hotels_unknown_city_not_404(client):
    resp = client.get(
        "/hotels/search",
        params={"city": "Atlantis", "check_in": VALID_CHECK_IN, "check_out": VALID_CHECK_OUT},
    )
    assert resp.status_code == 200


def test_search_hotels_echoes_back_params(client):
    body = client.get(
        "/hotels/search",
        params={
            "city": "Da Nang",
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "guests": 2,
        },
    ).json()
    assert body["search"]["city"] == "Da Nang"
    assert body["search"]["check_in"] == VALID_CHECK_IN
    assert body["search"]["check_out"] == VALID_CHECK_OUT
    assert body["search"]["guests"] == 2


def test_search_hotels_missing_city_returns_422(client):
    resp = client.get(
        "/hotels/search",
        params={"check_in": VALID_CHECK_IN, "check_out": VALID_CHECK_OUT},
    )
    assert resp.status_code == 422


def test_search_hotels_pagination(client):
    full = client.get(
        "/hotels/search",
        params={"city": "Da Nang", "check_in": VALID_CHECK_IN, "check_out": VALID_CHECK_OUT,
                "limit": 100},
    ).json()
    total = full["total"]
    if total > 1:
        page1 = client.get(
            "/hotels/search",
            params={"city": "Da Nang", "check_in": VALID_CHECK_IN, "check_out": VALID_CHECK_OUT,
                    "limit": 1, "offset": 0},
        ).json()
        page2 = client.get(
            "/hotels/search",
            params={"city": "Da Nang", "check_in": VALID_CHECK_IN, "check_out": VALID_CHECK_OUT,
                    "limit": 1, "offset": 1},
        ).json()
        assert page1["total"] == total
        assert page2["total"] == total
        assert page1["results"][0]["id"] != page2["results"][0]["id"]


# ---------------------------------------------------------------------------
# GET /hotels/{hotel_id}
# ---------------------------------------------------------------------------


def test_get_hotel_returns_200(client):
    hotel_id = get_first_hotel_id(client)
    assert client.get(f"/hotels/{hotel_id}").status_code == 200


def test_get_hotel_returns_correct_id(client):
    hotel_id = get_first_hotel_id(client)
    assert client.get(f"/hotels/{hotel_id}").json()["id"] == hotel_id


def test_get_hotel_has_expected_fields(client):
    hotel_id = get_first_hotel_id(client)
    body = client.get(f"/hotels/{hotel_id}").json()
    for field in ("id", "name", "city", "price_per_night", "star_rating", "amenities"):
        assert field in body


def test_get_hotel_nonexistent_returns_404(client):
    assert client.get("/hotels/00000000-0000-0000-0000-000000000000").status_code == 404


# ---------------------------------------------------------------------------
# POST /hotels/book
# ---------------------------------------------------------------------------


def test_book_hotel_returns_200(client):
    hotel_id = get_first_hotel_id(client)
    resp = client.post(
        "/hotels/book",
        json={
            "hotel_id": hotel_id,
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "guests": 2,
            "guest_name": "Alice Smith",
            "guest_email": "alice@example.com",
        },
    )
    assert resp.status_code == 200


def test_book_hotel_response_structure(client):
    hotel_id = get_first_hotel_id(client)
    body = client.post(
        "/hotels/book",
        json={
            "hotel_id": hotel_id,
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "guests": 1,
            "guest_name": "Bob Jones",
            "guest_email": "bob@example.com",
        },
    ).json()
    for field in (
        "id", "type", "reference_id", "customer_name",
        "customer_email", "total_price", "status", "created_at", "details",
    ):
        assert field in body


def test_book_hotel_type_is_hotel(client):
    hotel_id = get_first_hotel_id(client)
    body = client.post(
        "/hotels/book",
        json={
            "hotel_id": hotel_id,
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "guests": 1,
            "guest_name": "Carol White",
            "guest_email": "carol@example.com",
        },
    ).json()
    assert body["type"] == "hotel"


def test_book_hotel_id_is_uuid(client):
    import uuid as _uuid

    hotel_id = get_first_hotel_id(client)
    body = client.post(
        "/hotels/book",
        json={
            "hotel_id": hotel_id,
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "guests": 1,
            "guest_name": "Dave Brown",
            "guest_email": "dave@example.com",
        },
    ).json()
    _uuid.UUID(body["id"])


def test_book_hotel_status_is_confirmed(client):
    hotel_id = get_first_hotel_id(client)
    body = client.post(
        "/hotels/book",
        json={
            "hotel_id": hotel_id,
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "guests": 1,
            "guest_name": "Eve Green",
            "guest_email": "eve@example.com",
        },
    ).json()
    assert body["status"] == "confirmed"


def test_book_hotel_total_price_computed_server_side(client):
    """total_price = price_per_night * nights (2 nights here)."""
    hotel_id = get_first_hotel_id(client)
    hotel = client.get(f"/hotels/{hotel_id}").json()
    price_per_night = hotel["price_per_night"]
    body = client.post(
        "/hotels/book",
        json={
            "hotel_id": hotel_id,
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "guests": 1,
            "guest_name": "Frank Lee",
            "guest_email": "frank@example.com",
        },
    ).json()
    assert body["total_price"] == pytest.approx(price_per_night * 2)


def test_book_hotel_details_includes_nights(client):
    hotel_id = get_first_hotel_id(client)
    body = client.post(
        "/hotels/book",
        json={
            "hotel_id": hotel_id,
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "guests": 1,
            "guest_name": "Grace Hall",
            "guest_email": "grace@example.com",
        },
    ).json()
    assert body["details"]["nights"] == 2


def test_book_hotel_nonexistent_hotel_returns_404(client):
    resp = client.post(
        "/hotels/book",
        json={
            "hotel_id": "00000000-0000-0000-0000-000000000000",
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "guests": 1,
            "guest_name": "Ghost",
            "guest_email": "ghost@example.com",
        },
    )
    assert resp.status_code == 404


def test_book_hotel_missing_fields_returns_422(client):
    assert client.post("/hotels/book", json={"hotel_id": "h_dn_01"}).status_code == 422


# ---------------------------------------------------------------------------
# Hotel search filters
# ---------------------------------------------------------------------------


def test_search_hotels_filter_min_stars(client):
    results = client.get(
        "/hotels/search",
        params={
            "city": "Da Nang",
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "min_stars": 5,
        },
    ).json()["results"]
    assert all(h["star_rating"] >= 5 for h in results)


def test_search_hotels_filter_max_price(client):
    results = client.get(
        "/hotels/search",
        params={
            "city": "Bangkok",
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "max_price": 300,
        },
    ).json()["results"]
    assert all(h["price_per_night"] <= 300 for h in results)


def test_search_hotels_filter_amenities_pool(client):
    results = client.get(
        "/hotels/search",
        params={
            "city": "Da Nang",
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "amenities": ["Pool"],
        },
    ).json()["results"]
    for hotel in results:
        assert any(a.lower() == "pool" for a in hotel["amenities"])


def test_search_hotels_filter_amenities_multiple(client):
    results = client.get(
        "/hotels/search",
        params={
            "city": "Bangkok",
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "amenities": ["Pool", "Spa"],
        },
    ).json()["results"]
    for hotel in results:
        amenities_lower = [a.lower() for a in hotel["amenities"]]
        assert "pool" in amenities_lower
        assert "spa" in amenities_lower


def test_search_hotels_filters_echoed_back(client):
    body = client.get(
        "/hotels/search",
        params={
            "city": "Da Nang",
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "min_stars": 4,
            "max_price": 500,
        },
    ).json()
    assert body["search"]["min_stars"] == 4
    assert body["search"]["max_price"] == 500


def test_book_hotel_with_notes(client):
    hotel_id = get_first_hotel_id(client)
    body = client.post(
        "/hotels/book",
        json={
            "hotel_id": hotel_id,
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "guests": 2,
            "guest_name": "Notes Guest",
            "guest_email": "notesg@example.com",
            "notes": "Anniversary trip, request sea view room",
        },
    ).json()
    assert body["notes"] == "Anniversary trip, request sea view room"


def test_book_hotel_notes_optional(client):
    hotel_id = get_first_hotel_id(client)
    body = client.post(
        "/hotels/book",
        json={
            "hotel_id": hotel_id,
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "guests": 1,
            "guest_name": "Silent Guest",
            "guest_email": "silent@example.com",
        },
    ).json()
    assert body["notes"] is None
