"""Tests for GET / (service info endpoint) and docs exposure."""

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


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
