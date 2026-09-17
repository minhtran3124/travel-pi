"""End-to-end tests for the trip expense ledger feature."""

import pytest


def _create_trip(client):
    resp = client.post("/trips", json={"title": "E2E expense trip", "travelers": 1})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _set_budget(client, trip_id, **caps):
    resp = client.post(f"/trips/{trip_id}/budget", json=caps)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _post_expense(client, trip_id, **fields):
    resp = client.post(f"/trips/{trip_id}/expenses", json=fields)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_full_expense_lifecycle(client):
    trip = _create_trip(client)
    trip_id = trip["id"]

    _set_budget(client, trip_id, flights=500, hotels=400, activities=200, buffer=100)

    vnd_exp = _post_expense(
        client,
        trip_id,
        amount=50000,
        currency="VND",
        category="food",
        description="breakfast",
    )
    assert vnd_exp["currency"] == "VND"
    assert vnd_exp["amount"] == 50000
    vnd_usd = vnd_exp["amount_usd"]
    assert vnd_usd > 0
    # 50000 VND / ~25400 per USD ≈ 1.97 USD — just check reasonable range
    assert 1.0 < vnd_usd < 5.0

    usd_exp = _post_expense(
        client, trip_id, amount=20.0, currency="USD", category="transport"
    )
    assert usd_exp["amount_usd"] == pytest.approx(20.0, abs=0.01)

    resp = client.get(f"/trips/{trip_id}/expenses")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    ids = {e["id"] for e in body["results"]}
    assert vnd_exp["id"] in ids
    assert usd_exp["id"] in ids

    resp = client.get(f"/trips/{trip_id}/expenses/summary")
    assert resp.status_code == 200
    summary = resp.json()

    expected_total = pytest.approx(vnd_usd + 20.0, abs=0.05)
    assert summary["total_usd"] == expected_total
    assert summary["expense_count"] == 2

    cats = {c["category"] for c in summary["by_category"]}
    assert "food" in cats
    assert "transport" in cats

    currs = {c["currency"] for c in summary["by_currency"]}
    assert "VND" in currs
    assert "USD" in currs

    budget = summary["budget"]
    assert budget["expense_spent"] == pytest.approx(vnd_usd + 20.0, abs=0.05)
    assert budget["total_cap"] == pytest.approx(1200.0, abs=0.01)
    # total_remaining = total_cap - (booked_spent + expense_spent)
    assert budget["total_remaining"] is not None
    assert budget["total_remaining"] < budget["total_cap"]

    resp = client.patch(
        f"/trips/{trip_id}/expenses/{vnd_exp['id']}",
        json={"amount": 100000},
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["amount"] == 100000
    assert updated["amount_usd"] > vnd_usd

    resp = client.get(f"/trips/{trip_id}/expenses/summary")
    new_summary = resp.json()
    assert new_summary["total_usd"] > summary["total_usd"]

    resp = client.delete(f"/trips/{trip_id}/expenses/{usd_exp['id']}")
    assert resp.status_code == 204

    resp = client.get(f"/trips/{trip_id}/expenses")
    assert resp.json()["total"] == 1

    resp = client.get(f"/trips/{trip_id}/expenses/summary")
    final_summary = resp.json()
    assert final_summary["expense_count"] == 1
    assert final_summary["total_usd"] < new_summary["total_usd"]

    resp = client.get(f"/trips/{trip_id}/expenses/{usd_exp['id']}")
    assert resp.status_code == 404
