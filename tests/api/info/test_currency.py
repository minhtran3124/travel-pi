"""Tests for the /currency/convert endpoint (mock FX)."""

from fastapi.testclient import TestClient

# ── Happy path ────────────────────────────────────────────────────────────────


def test_convert_status(client: TestClient) -> None:
    resp = client.get(
        "/currency/convert", params={"from": "USD", "to": "VND", "amount": 100}
    )
    assert resp.status_code == 200


def test_convert_response_structure(client: TestClient) -> None:
    data = client.get(
        "/currency/convert", params={"from": "USD", "to": "VND", "amount": 100}
    ).json()
    for field in ("from", "to", "rate", "amount", "converted", "last_updated"):
        assert field in data, f"missing field: {field}"
    assert data["from"] == "USD"
    assert data["to"] == "VND"
    assert data["amount"] == 100
    assert data["converted"] == round(data["rate"] * 100, 2)
    assert data["local_currency"] is None


def test_convert_same_currency_is_identity(client: TestClient) -> None:
    data = client.get("/currency/convert", params={"to": "USD", "amount": 250}).json()
    assert data["from"] == "USD"  # default source
    assert data["rate"] == 1.0
    assert data["converted"] == 250.0


def test_convert_codes_are_case_insensitive(client: TestClient) -> None:
    data = client.get(
        "/currency/convert", params={"from": "usd", "to": "jpy", "amount": 1}
    ).json()
    assert data["from"] == "USD"
    assert data["to"] == "JPY"


def test_convert_cross_rate(client: TestClient) -> None:
    """Non-USD pair: rate must equal RATES[to]/RATES[from]."""
    from app.data.fx import RATES

    data = client.get(
        "/currency/convert", params={"from": "EUR", "to": "THB", "amount": 10}
    ).json()
    assert data["rate"] == round(RATES["THB"] / RATES["EUR"], 6)


# ── local_currency from country ─────────────────────────────────────────────────


def test_convert_attaches_local_currency_fuzzy(client: TestClient) -> None:
    data = client.get(
        "/currency/convert",
        params={"from": "USD", "to": "EUR", "amount": 1, "country": "vietnam"},
    ).json()
    assert data["local_currency"] == {"code": "VND", "name": "Vietnamese Dong"}


def test_convert_unknown_country_yields_no_local_currency(client: TestClient) -> None:
    data = client.get(
        "/currency/convert",
        params={"from": "USD", "to": "EUR", "amount": 1, "country": "Narnia"},
    ).json()
    assert data["local_currency"] is None


# ── Errors / edges ───────────────────────────────────────────────────────────


def test_convert_unknown_code_is_404(client: TestClient) -> None:
    resp = client.get(
        "/currency/convert", params={"from": "USD", "to": "XXX", "amount": 1}
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "NotFoundError"


def test_convert_zero_amount_is_422(client: TestClient) -> None:
    resp = client.get(
        "/currency/convert", params={"from": "USD", "to": "VND", "amount": 0}
    )
    assert resp.status_code == 422


def test_convert_negative_amount_is_422(client: TestClient) -> None:
    resp = client.get(
        "/currency/convert", params={"from": "USD", "to": "VND", "amount": -5}
    )
    assert resp.status_code == 422


def test_convert_missing_to_is_422(client: TestClient) -> None:
    resp = client.get("/currency/convert", params={"from": "USD", "amount": 100})
    assert resp.status_code == 422
