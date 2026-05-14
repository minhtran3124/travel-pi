"""Tests for GET /cities (paginated)."""


def _all_cities(client, **params):
    """Fetch all cities (high limit to bypass pagination)."""
    return client.get("/cities", params={"limit": 500, **params}).json()["results"]


# ---------------------------------------------------------------------------
# GET /cities  (paginated)
# ---------------------------------------------------------------------------


def test_list_cities_returns_200(client):
    assert client.get("/cities").status_code == 200


def test_list_cities_returns_paginated_envelope(client):
    body = client.get("/cities").json()
    for field in ("total", "limit", "offset", "results"):
        assert field in body
    assert isinstance(body["results"], list)
    assert body["total"] > 0


def test_city_has_required_fields(client):
    city = client.get("/cities").json()["results"][0]
    for field in ("name", "country", "airport_codes", "hotel_count"):
        assert field in city


def test_city_airport_codes_is_list(client):
    for city in _all_cities(client):
        assert isinstance(city["airport_codes"], list)


def test_city_hotel_count_non_negative(client):
    for city in _all_cities(client):
        assert city["hotel_count"] >= 0


def test_some_cities_have_hotels(client):
    assert any(c["hotel_count"] > 0 for c in _all_cities(client))


def test_filter_by_country(client):
    cities = _all_cities(client, country="Vietnam")
    assert len(cities) > 0
    for city in cities:
        assert city["country"] == "Vietnam"


def test_filter_has_hotels_true(client):
    cities = _all_cities(client, has_hotels="true")
    assert len(cities) > 0
    for city in cities:
        assert city["hotel_count"] > 0


def test_filter_has_hotels_false(client):
    cities = _all_cities(client, has_hotels="false")
    for city in cities:
        assert city["hotel_count"] == 0


def test_get_city_by_name(client):
    resp = client.get("/cities/Da Nang")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Da Nang"


def test_get_city_not_found(client):
    assert client.get("/cities/Atlantis").status_code == 404


def test_total_cities_covers_airports_and_hotels(client):
    """At least 49 cities — 48 airport cities + Hoi An from hotels."""
    body = client.get("/cities").json()
    assert body["total"] >= 49


def test_cities_include_da_nang(client):
    names = [c["name"] for c in _all_cities(client)]
    assert "Da Nang" in names


def test_cities_count_matches_hotel_data(client):
    cities = _all_cities(client)
    total_hotels = client.get("/hotels", params={"limit": 1}).json()["total"]
    total_from_cities = sum(c["hotel_count"] for c in cities)
    assert total_from_cities == total_hotels


def test_city_country_is_string(client):
    for city in _all_cities(client):
        assert isinstance(city["country"], str)
        assert city["country"]


# Pagination behaviour
def test_cities_default_limit(client):
    body = client.get("/cities").json()
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert len(body["results"]) <= 20


def test_cities_custom_limit(client):
    body = client.get("/cities", params={"limit": 5}).json()
    assert body["limit"] == 5
    assert len(body["results"]) <= 5


def test_cities_offset_shifts_page(client):
    all_names = [c["name"] for c in _all_cities(client)]
    p1 = [c["name"] for c in
          client.get("/cities", params={"limit": 3, "offset": 0}).json()["results"]]
    p2 = [c["name"] for c in
          client.get("/cities", params={"limit": 3, "offset": 3}).json()["results"]]
    assert p1 == all_names[:3]
    assert p2 == all_names[3:6]


def test_cities_total_stable_across_pages(client):
    t1 = client.get("/cities", params={"limit": 5, "offset": 0}).json()["total"]
    t2 = client.get("/cities", params={"limit": 5, "offset": 10}).json()["total"]
    assert t1 == t2


def test_cities_limit_validation(client):
    assert client.get("/cities", params={"limit": 0}).status_code == 422
    assert client.get("/cities", params={"limit": 501}).status_code == 422


def test_cities_offset_validation(client):
    assert client.get("/cities", params={"offset": -1}).status_code == 422
