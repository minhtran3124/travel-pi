"""Tests for GET /airports (paginated)."""


def test_list_airports_returns_200(client):
    assert client.get("/airports").status_code == 200


def test_list_airports_returns_paginated_envelope(client):
    body = client.get("/airports").json()
    for field in ("total", "limit", "offset", "results"):
        assert field in body
    assert isinstance(body["results"], list)
    assert body["total"] > 0


def test_airport_has_required_fields(client):
    airport = client.get("/airports").json()["results"][0]
    for field in ("code", "name", "city", "country"):
        assert field in airport


def test_airport_code_is_three_letters(client):
    for airport in client.get("/airports", params={"limit": 100}).json()["results"]:
        assert len(airport["code"]) == 3
        assert airport["code"].isupper()


def test_airport_fields_are_strings(client):
    airport = client.get("/airports").json()["results"][0]
    for field in ("code", "name", "city", "country"):
        assert isinstance(airport[field], str)
        assert airport[field]


def test_airports_default_limit(client):
    body = client.get("/airports").json()
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert len(body["results"]) <= 20


def test_airports_custom_limit(client):
    body = client.get("/airports", params={"limit": 5}).json()
    assert body["limit"] == 5
    assert len(body["results"]) <= 5


def test_airports_offset_shifts_page(client):
    all_codes = [a["code"] for a in
                 client.get("/airports", params={"limit": 100}).json()["results"]]
    p1 = [a["code"] for a in
          client.get("/airports", params={"limit": 3, "offset": 0}).json()["results"]]
    p2 = [a["code"] for a in
          client.get("/airports", params={"limit": 3, "offset": 3}).json()["results"]]
    assert p1 == all_codes[:3]
    assert p2 == all_codes[3:6]


def test_airports_total_stable_across_pages(client):
    t1 = client.get("/airports", params={"limit": 5, "offset": 0}).json()["total"]
    t2 = client.get("/airports", params={"limit": 5, "offset": 10}).json()["total"]
    assert t1 == t2


def test_airports_limit_validation(client):
    assert client.get("/airports", params={"limit": 0}).status_code == 422
    assert client.get("/airports", params={"limit": 501}).status_code == 422


def test_airports_offset_validation(client):
    assert client.get("/airports", params={"offset": -1}).status_code == 422


# ---------------------------------------------------------------------------
# GET /airports?q=  (fuzzy search)
# ---------------------------------------------------------------------------


def _all_airports(client, **params):
    return client.get("/airports", params={"limit": 500, **params}).json()["results"]


def test_airports_fuzzy_by_iata_code(client):
    results = _all_airports(client, q="DAD")
    assert results
    assert results[0]["code"] == "DAD"


def test_airports_fuzzy_code_case_insensitive(client):
    results = _all_airports(client, q="dad")
    assert any(a["code"] == "DAD" for a in results)


def test_airports_fuzzy_by_city(client):
    results = _all_airports(client, q="Da Nang")
    assert any(a["city"] == "Da Nang" for a in results)


def test_airports_fuzzy_partial_city(client):
    results = _all_airports(client, q="danang")
    assert any(a["city"] == "Da Nang" for a in results)


def test_airports_fuzzy_by_name(client):
    results = _all_airports(client, q="International")
    assert results
    assert all("international" in a["name"].lower() for a in results)


def test_airports_fuzzy_no_match_returns_empty(client):
    body = client.get("/airports", params={"q": "zzzznowhere"}).json()
    assert body["results"] == []
    assert body["total"] == 0
