"""REST consistency: currency validation status, budget vs expenses, ?city= filter on list endpoints."""


def _trip(client):
    resp = client.post("/trips", json={"title": "Consistency", "travelers": 1})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_unknown_currency_is_422_not_404(client):
    trip_id = _trip(client)
    resp = client.post(
        f"/trips/{trip_id}/expenses",
        json={"category": "food", "amount": 10, "currency": "ZZZ"},
    )
    assert resp.status_code == 422, resp.text


def test_trip_budget_total_spent_includes_expenses(client):
    trip_id = _trip(client)
    resp = client.post(
        f"/trips/{trip_id}/expenses",
        json={"category": "food", "amount": 25, "currency": "USD"},
    )
    assert resp.status_code == 201, resp.text
    budget = client.get(f"/trips/{trip_id}/budget").json()
    summary = client.get(f"/trips/{trip_id}/expenses/summary").json()
    assert budget["total_spent"] == summary["budget"]["total_spent"] == 25
    assert summary["budget"]["booked_spent"] == 0
    assert summary["budget"]["expense_spent"] == 25


def test_list_places_honours_city_filter(client):
    all_places = client.get("/places?limit=200").json()
    city = all_places["results"][0]["city"]
    filtered = client.get("/places", params={"city": city, "limit": 200}).json()
    assert 0 < filtered["total"] < all_places["total"]
    assert {p["city"] for p in filtered["results"]} == {city}


def test_list_hotels_honours_city_filter(client):
    all_hotels = client.get("/hotels?limit=200").json()
    city = all_hotels["results"][0]["city"]
    filtered = client.get("/hotels", params={"city": city, "limit": 200}).json()
    assert 0 < filtered["total"] < all_hotels["total"]
    assert {h["city"] for h in filtered["results"]} == {city}
