"""API-level tests for /trips/{trip_id}/expenses endpoints."""


def _create_trip(client):
    resp = client.post("/trips", json={"title": "Expense test trip", "travelers": 1})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_expense(client, trip_id, **overrides):
    body = {
        "category": "food",
        "amount": 50000,
        "currency": "VND",
        "description": "breakfast",
    }
    body.update(overrides)
    resp = client.post(f"/trips/{trip_id}/expenses", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_expense_201(client):
    trip = _create_trip(client)
    resp = client.post(
        f"/trips/{trip['id']}/expenses",
        json={"category": "food", "amount": 50000, "currency": "VND"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["category"] == "food"
    assert body["currency"] == "VND"
    assert body["amount"] == 50000
    assert body["amount_usd"] > 0
    assert body["fx_rate"] > 0
    assert body["short_code"].startswith("EXP-")
    assert body["trip_id"] == trip["id"]


def test_create_expense_currency_normalized(client):
    trip = _create_trip(client)
    resp = client.post(
        f"/trips/{trip['id']}/expenses",
        json={"category": "transport", "amount": 10, "currency": " usd "},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["currency"] == "USD"


def test_create_expense_amount_zero_422(client):
    trip = _create_trip(client)
    resp = client.post(
        f"/trips/{trip['id']}/expenses",
        json={"category": "food", "amount": 0, "currency": "USD"},
    )
    assert resp.status_code == 422


def test_create_expense_amount_negative_422(client):
    trip = _create_trip(client)
    resp = client.post(
        f"/trips/{trip['id']}/expenses",
        json={"category": "food", "amount": -5, "currency": "USD"},
    )
    assert resp.status_code == 422


def test_create_expense_unknown_trip_404(client):
    resp = client.post(
        "/trips/no-such-trip/expenses",
        json={"category": "food", "amount": 10, "currency": "USD"},
    )
    assert resp.status_code == 404


def test_create_expense_unknown_currency_422(client):
    trip = _create_trip(client)
    resp = client.post(
        f"/trips/{trip['id']}/expenses",
        json={"category": "food", "amount": 10, "currency": "XYZ"},
    )
    assert resp.status_code == 422


def test_list_expenses_200(client):
    trip = _create_trip(client)
    _create_expense(client, trip["id"])
    _create_expense(client, trip["id"], category="transport", currency="USD", amount=5)
    resp = client.get(f"/trips/{trip['id']}/expenses")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert len(body["results"]) == 2


def test_list_expenses_category_filter(client):
    trip = _create_trip(client)
    _create_expense(client, trip["id"], category="food")
    _create_expense(client, trip["id"], category="transport", currency="USD", amount=5)
    resp = client.get(f"/trips/{trip['id']}/expenses?category=food")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["results"][0]["category"] == "food"


def test_list_expenses_unknown_trip_404(client):
    resp = client.get("/trips/no-such-trip/expenses")
    assert resp.status_code == 404


def test_get_expense_summary_200(client):
    trip = _create_trip(client)
    _create_expense(client, trip["id"], category="food", amount=50000, currency="VND")
    _create_expense(client, trip["id"], category="transport", amount=10, currency="USD")
    resp = client.get(f"/trips/{trip['id']}/expenses/summary")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["expense_count"] == 2
    assert body["total_usd"] > 0
    cats = {c["category"] for c in body["by_category"]}
    assert "food" in cats
    assert "transport" in cats
    currs = {c["currency"] for c in body["by_currency"]}
    assert "VND" in currs
    assert "USD" in currs
    assert body["budget"]["total_cap"] is None
    assert body["budget"]["over_budget"] is False


def test_summary_route_not_swallowed_by_expense_id(client):
    """GET /summary must resolve before /{expense_id}."""
    trip = _create_trip(client)
    resp = client.get(f"/trips/{trip['id']}/expenses/summary")
    assert resp.status_code == 200


def test_get_expense_200(client):
    trip = _create_trip(client)
    exp = _create_expense(client, trip["id"])
    resp = client.get(f"/trips/{trip['id']}/expenses/{exp['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == exp["id"]


def test_get_expense_unknown_404(client):
    trip = _create_trip(client)
    resp = client.get(f"/trips/{trip['id']}/expenses/no-such-id")
    assert resp.status_code == 404


def test_patch_expense_200(client):
    trip = _create_trip(client)
    exp = _create_expense(client, trip["id"], amount=100, currency="USD")
    resp = client.patch(
        f"/trips/{trip['id']}/expenses/{exp['id']}",
        json={"amount": 200},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["amount"] == 200
    assert body["amount_usd"] > exp["amount_usd"]


def test_delete_expense_204(client):
    trip = _create_trip(client)
    exp = _create_expense(client, trip["id"])
    resp = client.delete(f"/trips/{trip['id']}/expenses/{exp['id']}")
    assert resp.status_code == 204
    resp2 = client.get(f"/trips/{trip['id']}/expenses/{exp['id']}")
    assert resp2.status_code == 404


def test_delete_expense_unknown_404(client):
    trip = _create_trip(client)
    resp = client.delete(f"/trips/{trip['id']}/expenses/no-such-id")
    assert resp.status_code == 404
