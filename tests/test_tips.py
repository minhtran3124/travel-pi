"""Tests for the /tips endpoint."""

from fastapi.testclient import TestClient

VALID_CATEGORIES = {
    "transport", "money", "safety", "culture", "food",
    "connectivity", "health", "etiquette", "best_time", "language",
}


# ── Basic shape ───────────────────────────────────────────────────────────────

def test_tips_by_country_status(client: TestClient) -> None:
    resp = client.get("/tips", params={"country": "Vietnam"})
    assert resp.status_code == 200


def test_tips_response_structure(client: TestClient) -> None:
    data = client.get("/tips", params={"country": "Vietnam"}).json()
    for field in ("city", "country", "count", "summary", "tips"):
        assert field in data, f"missing field: {field}"
    assert isinstance(data["tips"], list)
    assert data["count"] == len(data["tips"])
    assert data["count"] > 0
    assert data["country"] == "Vietnam"
    assert data["city"] is None
    assert isinstance(data["summary"], str) and data["summary"]


def test_tip_item_fields(client: TestClient) -> None:
    tip = client.get("/tips", params={"country": "Vietnam"}).json()["tips"][0]
    for field in ("id", "category", "scope", "title", "content", "is_essential"):
        assert field in tip, f"missing field: {field}"
    assert tip["category"] in VALID_CATEGORIES
    assert tip["scope"] in {"country", "city"}
    assert isinstance(tip["is_essential"], bool)


def test_country_tips_all_country_scope(client: TestClient) -> None:
    tips = client.get("/tips", params={"country": "Vietnam"}).json()["tips"]
    assert all(t["scope"] == "country" for t in tips)


# ── Resolving country from city ───────────────────────────────────────────────

def test_tips_by_city_resolves_country(client: TestClient) -> None:
    data = client.get("/tips", params={"city": "Hanoi"}).json()
    assert data["city"] == "Hanoi"
    assert data["country"] == "Vietnam"
    assert data["count"] > 0


def test_tips_by_city_includes_country_tips(client: TestClient) -> None:
    """A city query must still surface the country-level tips."""
    tips = client.get("/tips", params={"city": "Hanoi"}).json()["tips"]
    assert any(t["scope"] == "country" for t in tips)


def test_tips_city_with_city_specific_tips(client: TestClient) -> None:
    """Hanoi has city-scoped tips seeded — they must appear alongside country tips."""
    tips = client.get("/tips", params={"city": "Hanoi"}).json()["tips"]
    assert any(t["scope"] == "city" for t in tips)


def test_tips_city_case_insensitive(client: TestClient) -> None:
    lower = client.get("/tips", params={"city": "hanoi"}).json()
    upper = client.get("/tips", params={"city": "HANOI"}).json()
    assert lower["count"] == upper["count"] > 0


def test_tips_country_case_insensitive(client: TestClient) -> None:
    lower = client.get("/tips", params={"country": "vietnam"}).json()
    upper = client.get("/tips", params={"country": "VIETNAM"}).json()
    assert lower["count"] == upper["count"] > 0


# ── Unknown locations ─────────────────────────────────────────────────────────

def test_tips_unknown_city_returns_empty(client: TestClient) -> None:
    resp = client.get("/tips", params={"city": "Atlantis"})
    data = resp.json()
    assert resp.status_code == 200
    assert data["count"] == 0
    assert data["tips"] == []


def test_tips_unknown_country_returns_empty(client: TestClient) -> None:
    resp = client.get("/tips", params={"country": "Narnia"})
    data = resp.json()
    assert resp.status_code == 200
    assert data["count"] == 0
    assert data["tips"] == []


# ── Filters ───────────────────────────────────────────────────────────────────

def test_tips_filter_by_category(client: TestClient) -> None:
    data = client.get("/tips", params={"country": "Vietnam", "category": "money"}).json()
    assert data["count"] > 0
    assert all(t["category"] == "money" for t in data["tips"])


def test_tips_invalid_category_422(client: TestClient) -> None:
    resp = client.get("/tips", params={"country": "Vietnam", "category": "bogus"})
    assert resp.status_code == 422


def test_tips_essential_only(client: TestClient) -> None:
    data = client.get("/tips", params={"country": "Vietnam", "essential_only": True}).json()
    assert data["count"] > 0
    assert all(t["is_essential"] is True for t in data["tips"])


# ── Required params ───────────────────────────────────────────────────────────

def test_tips_no_params_is_422(client: TestClient) -> None:
    """Must provide city or country — the response carries a single country."""
    resp = client.get("/tips")
    assert resp.status_code == 422


def test_tips_empty_strings_treated_as_missing(client: TestClient) -> None:
    """HTML forms send empty strings — treated as missing, so 422."""
    resp = client.get("/tips", params={"city": "", "country": ""})
    assert resp.status_code == 422


# ── Fuzzy city / country matching ─────────────────────────────────────────────

def test_tips_city_is_fuzzy(client: TestClient) -> None:
    data = client.get("/tips", params={"city": "danang"}).json()
    assert data["city"] == "Da Nang"
    assert data["country"] == "Vietnam"
    assert data["count"] > 0


def test_tips_country_is_fuzzy(client: TestClient) -> None:
    data = client.get("/tips", params={"country": "viet nam"}).json()
    assert data["country"] == "Vietnam"
    assert data["count"] > 0


def test_tips_unknown_city_still_zero(client: TestClient) -> None:
    data = client.get("/tips", params={"city": "zzzznowhere"}).json()
    assert data["count"] == 0


# ── Dashboard /dashboard/tips: shows all tips by default ─────────────────────


def test_dashboard_tips_no_filter_returns_200(client: TestClient) -> None:
    """Landing on /dashboard/tips with no filters should render, not 422."""
    assert client.get("/dashboard/tips").status_code == 200


def test_dashboard_tips_no_filter_renders_tip_cards(client: TestClient) -> None:
    """Default view shows the every-destination tip list, not the picker."""
    html = client.get("/dashboard/tips").text
    assert "tip-card" in html
    # Each card carries its location chip in the all-tips view.
    assert "loc-badge" in html


def test_dashboard_tips_category_filter_narrows_results(client: TestClient) -> None:
    """A category filter applied to the all-tips view yields fewer cards."""
    all_count = client.get("/dashboard/tips").text.count("tip-card")
    money_count = client.get(
        "/dashboard/tips", params={"category": "money"}
    ).text.count("tip-card")
    assert 0 < money_count < all_count


# ── tip_service.get_all_tips: unit-level coverage ─────────────────────────────


def test_get_all_tips_includes_country_and_city_scopes(client: TestClient) -> None:
    from app.services import tip_service

    result = tip_service.get_all_tips()
    scopes = {t.scope for t in result.tips}
    assert scopes == {"country", "city"}
    # Every tip in the all view carries a location, so the UI can label it.
    assert all(t.location for t in result.tips)


def test_get_all_tips_essential_only_filter(client: TestClient) -> None:
    from app.services import tip_service

    essential = tip_service.get_all_tips(essential_only=True)
    assert essential.count > 0
    assert all(t.is_essential for t in essential.tips)
