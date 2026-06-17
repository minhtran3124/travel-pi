"""Tests for the /visa endpoint (static entry-requirement guidance)."""

from app.data.visa import COUNTRY_VISA
from fastapi.testclient import TestClient

# ── Happy path ────────────────────────────────────────────────────────────────


def test_visa_status(client: TestClient) -> None:
    assert client.get("/visa", params={"country": "Vietnam"}).status_code == 200


def test_visa_response_structure(client: TestClient) -> None:
    data = client.get("/visa", params={"country": "Vietnam"}).json()
    assert data["country"] == "Vietnam"
    assert data["found"] is True
    assert data["disclaimer"]
    entry = data["entry"]
    assert entry["visa_free_days"] == COUNTRY_VISA["Vietnam"]["visa_free_days"]
    for field in (
        "visa_free_days",
        "visa_on_arrival",
        "e_visa",
        "passport_validity_months",
        "summary",
    ):
        assert field in entry, f"missing field: {field}"


# ── Fuzzy resolution ────────────────────────────────────────────────────────────


def test_visa_city_resolves_country(client: TestClient) -> None:
    data = client.get("/visa", params={"city": "danang"}).json()
    assert data["country"] == "Vietnam"
    assert data["city"] == "Da Nang"
    assert data["found"] is True


def test_visa_country_fuzzy(client: TestClient) -> None:
    data = client.get("/visa", params={"country": "viet nam"}).json()
    assert data["country"] == "Vietnam"
    assert data["found"] is True


# ── Edge cases ──────────────────────────────────────────────────────────────────


def test_visa_unknown_country_is_not_found(client: TestClient) -> None:
    data = client.get("/visa", params={"country": "Xanadu"}).json()
    assert data["found"] is False
    assert data["entry"] is None


def test_visa_visa_required_country_still_found(client: TestClient) -> None:
    """A country with visa_free_days == 0 is still a real, found record."""
    assert COUNTRY_VISA["Cambodia"]["visa_free_days"] == 0
    data = client.get("/visa", params={"country": "Cambodia"}).json()
    assert data["found"] is True
    assert data["entry"]["visa_free_days"] == 0


def test_visa_requires_a_param(client: TestClient) -> None:
    assert client.get("/visa").status_code == 422


# ── Dashboard /dashboard/visa ─────────────────────────────────────────────────


def test_dashboard_visa_no_filter_returns_200(client: TestClient) -> None:
    """Landing on /dashboard/visa with no params renders the picker, not a 422."""
    assert client.get("/dashboard/visa").status_code == 200


def test_dashboard_visa_no_filter_renders_picker(client: TestClient) -> None:
    """Default view is the country picker — a grid of passport-page tiles."""
    html = client.get("/dashboard/visa").text
    assert 'class="page' in html
    assert "Pick a destination" in html


def test_dashboard_visa_country_renders_entry_card(client: TestClient) -> None:
    """A selected country shows its entry record with the quotable summary."""
    html = client.get("/dashboard/visa", params={"country": "Vietnam"}).text
    assert 'class="record"' in html
    assert COUNTRY_VISA["Vietnam"]["summary"] in html
    assert "Entry record" in html


def test_dashboard_visa_city_resolves_country(client: TestClient) -> None:
    """A city resolves to its country's record (and offers the explore strip)."""
    html = client.get("/dashboard/visa", params={"city": "Da Nang"}).text
    assert 'class="record"' in html
    assert "Vietnam" in html


def test_dashboard_visa_unknown_country_shows_empty_state(client: TestClient) -> None:
    """An unrecognised destination renders the friendly empty state, not a 500."""
    resp = client.get("/dashboard/visa", params={"country": "Xanadu"})
    assert resp.status_code == 200
    assert "No entry guidance" in resp.text
