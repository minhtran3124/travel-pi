"""Request-ID propagation and GZip compression middleware."""

from fastapi.testclient import TestClient


def test_request_id_generated(client: TestClient):
    resp = client.get("/")
    rid = resp.headers.get("X-Request-ID")
    assert rid and len(rid) >= 8


def test_request_id_echoed(client: TestClient):
    resp = client.get("/", headers={"X-Request-ID": "abc-123"})
    assert resp.headers["X-Request-ID"] == "abc-123"


def test_gzip_compresses_large_response(client: TestClient):
    # /flights/search returns a large JSON list; ask for gzip explicitly.
    resp = client.get(
        "/flights/search",
        params={"origin": "DAD", "destination": "SGN", "departure_date": "2026-12-01"},
        headers={"Accept-Encoding": "gzip"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("content-encoding") == "gzip"
