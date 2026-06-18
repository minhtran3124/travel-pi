"""Tests for the health/readiness endpoints."""

import pytest
from app.services.booking_service import BookingService
from fastapi.testclient import TestClient


def test_healthz_ok(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readyz_ready(client: TestClient) -> None:
    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["routing_provider"] in {"live", "fallback"}


def test_readyz_degrades_when_db_unreachable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A DB failure makes /readyz report not_ready — it must not 500."""

    def _boom(self: BookingService) -> bool:
        raise RuntimeError("db down")

    monkeypatch.setattr(BookingService, "ping", _boom)
    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"] == "error"
