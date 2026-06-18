"""Every response advertises informational (unenforced) rate-limit headers."""

from fastapi.testclient import TestClient


def test_rate_limit_headers_present(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.headers["X-RateLimit-Limit"].isdigit()
    assert resp.headers["X-RateLimit-Remaining"].isdigit()
    assert resp.headers["X-RateLimit-Reset"].isdigit()
