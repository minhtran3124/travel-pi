"""Tests for GET / (service info endpoint) and docs exposure."""

from app.core.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_root_returns_200(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_root_response_has_required_fields(client):
    body = client.get("/").json()
    assert "name" in body
    assert "docs" in body
    assert "endpoints" in body


def test_root_endpoints_is_list(client):
    body = client.get("/").json()
    assert isinstance(body["endpoints"], list)
    assert len(body["endpoints"]) > 0


def test_root_name_is_string(client):
    body = client.get("/").json()
    assert isinstance(body["name"], str)
    assert body["name"]


# --- Docs exposure by environment --------------------------------------------


def test_docs_exposed_in_development(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_docs_hidden_in_production(monkeypatch):
    monkeypatch.setattr(
        "app.main.get_settings", lambda: Settings(environment="production")
    )
    with TestClient(create_app()) as prod_client:
        assert prod_client.get("/docs").status_code == 404
        assert prod_client.get("/redoc").status_code == 404
        assert prod_client.get("/openapi.json").status_code == 404


# --- OpenAPI schema correctness ----------------------------------------------


def test_openapi_serves_and_redoc_renders(client):
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/redoc").status_code == 200


def test_openapi_documents_error_envelope(client):
    """Error responses are documented with the ErrorResponse envelope, not
    the stale default HTTPValidationError shape."""
    spec = client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]
    assert "ErrorResponse" in schemas
    assert set(schemas["ErrorResponse"]["properties"]) == {
        "error",
        "message",
        "status_code",
        "path",
        "hint",
        "errors",
    }

    def error_ref(operation, code):
        schema = operation["responses"][code]["content"]["application/json"]["schema"]
        return schema.get("$ref", "").split("/")[-1]

    # 404 + 422 on a lookup route, 409 on hotel booking — all the envelope.
    get_booking = spec["paths"]["/bookings/{booking_id}"]["get"]
    assert error_ref(get_booking, "404") == "ErrorResponse"
    assert error_ref(get_booking, "422") == "ErrorResponse"
    book_hotel = spec["paths"]["/hotels/book"]["post"]
    assert error_ref(book_hotel, "409") == "ErrorResponse"


def test_openapi_hotel_availability_schema_inherits_hotel(client):
    """HotelAvailability must carry every Hotel field plus the availability ones."""
    spec = client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]
    hotel_fields = set(schemas["Hotel"]["properties"])
    avail_fields = set(schemas["HotelAvailability"]["properties"])
    # Every Hotel field is present, plus the five availability-specific ones.
    assert hotel_fields <= avail_fields
    assert avail_fields - hotel_fields == {
        "available",
        "available_rooms",
        "max_occupancy_per_room",
        "nights",
        "total_price",
    }
