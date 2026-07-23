"""Tests for the consistent error envelope.

Every failure — domain (``AppError``), HTTP (``HTTPException``), or
request-validation — must come back in the same JSON shape so an API
consumer can parse errors uniformly:
    {"error", "message", "status_code", "path", ["errors"]}
"""

ENVELOPE_FIELDS = ("error", "message", "status_code", "path")


def _assert_envelope(body, status_code, path):
    for field in ENVELOPE_FIELDS:
        assert field in body, f"missing '{field}' in error body: {body}"
    assert body["status_code"] == status_code
    assert body["path"] == path
    assert isinstance(body["error"], str) and body["error"]
    assert isinstance(body["message"], str) and body["message"]


# --- AppError (domain) -------------------------------------------------------


def test_app_error_404_uses_envelope(client):
    path = "/bookings/00000000-0000-0000-0000-000000000000"
    resp = client.get(path)
    assert resp.status_code == 404
    _assert_envelope(resp.json(), 404, path)


def test_app_error_names_the_exception_class(client):
    body = client.get("/cities/NoSuchCity").json()
    assert body["error"] == "NotFoundError"


# --- HTTPException raised directly by a router -------------------------------


def test_http_exception_bad_date_uses_envelope(client):
    path = "/flights/search"
    resp = client.get(
        path,
        params={"origin": "DAD", "destination": "SGN", "departure_date": "not-a-date"},
    )
    assert resp.status_code == 422
    _assert_envelope(resp.json(), 422, path)


# --- Unmatched route (Starlette's own 404) -----------------------------------


def test_unknown_route_uses_envelope(client):
    path = "/this/route/does/not/exist"
    resp = client.get(path)
    assert resp.status_code == 404
    body = resp.json()
    _assert_envelope(body, 404, path)
    # Route-not-found 404 must be distinguishable from a domain NotFoundError —
    # the envelope's ``error`` field is mapped from the status code.
    assert body["error"] == "NotFound"


def test_method_not_allowed_envelope_label(client):
    """A POST to a GET-only route gets a labelled 405 envelope."""
    resp = client.post("/airports")
    assert resp.status_code == 405
    assert resp.json()["error"] == "MethodNotAllowed"


def test_non_enforced_error_keeps_nominal_rate_limit_headers(client):
    from app.core.config import get_settings

    response = client.get("/this/route/does/not/exist")
    nominal = str(get_settings().rate_limit_nominal)
    assert response.headers["x-ratelimit-limit"] == nominal
    assert response.headers["x-ratelimit-remaining"] == nominal


def test_metadata_less_rate_limit_error_omits_unknown_capacity_headers():
    from app.exceptions import RateLimitError
    from app.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()

    @app.get("/__manual-rate-limit")
    def _manual_rate_limit():
        raise RateLimitError(retry_after=7)

    response = TestClient(app).get("/__manual-rate-limit")
    assert response.status_code == 429
    assert response.headers["retry-after"] == "7"
    assert "x-ratelimit-limit" not in response.headers
    assert "x-ratelimit-remaining" not in response.headers
    assert "x-ratelimit-reset" not in response.headers
    assert response.json()["error"] == "RateLimitError"


# --- Request validation (422) ------------------------------------------------


def test_validation_error_uses_envelope(client):
    path = "/airports"
    resp = client.get(path, params={"limit": 0})
    assert resp.status_code == 422
    body = resp.json()
    _assert_envelope(body, 422, path)
    assert body["error"] == "ValidationError"


def test_validation_error_includes_field_details(client):
    body = client.get("/airports", params={"limit": 0}).json()
    assert "errors" in body
    assert isinstance(body["errors"], list)
    assert len(body["errors"]) >= 1


def test_validation_error_on_missing_required_body(client):
    # POST /flights/book with an empty body — missing required fields.
    path = "/flights/book"
    resp = client.post(path, json={})
    assert resp.status_code == 422
    _assert_envelope(resp.json(), 422, path)


# --- Recovery hints ----------------------------------------------------------


def test_domain_error_includes_actionable_hint(client):
    """AppError hints — what an agent should try next — appear in the envelope."""
    body = client.get("/bookings/no-such-booking").json()
    assert "hint" in body and isinstance(body["hint"], str) and body["hint"]
    # The hint should point at a concrete recovery action.
    assert "GET /bookings" in body["hint"] or "confirmation_code" in body["hint"]


def test_404_for_unknown_hotel_hints_at_search(client):
    body = client.get("/hotels/00000000-0000-0000-0000-000000000000").json()
    assert "GET /hotels" in body["hint"]


def test_404_for_unknown_flight_hints_at_search(client):
    body = client.get("/flights/no-such-flight").json()
    assert "GET /flights/search" in body["hint"]


def test_validation_error_has_recovery_hint(client):
    body = client.get("/airports", params={"limit": 0}).json()
    assert body.get("hint") and "errors" in body["hint"]


def test_route_not_found_has_no_hint(client):
    """Unmatched-route 404s come from Starlette and don't carry a domain hint."""
    body = client.get("/this/route/does/not/exist").json()
    assert "hint" not in body or body.get("hint") is None


# --- Unhandled (non-AppError) exceptions — the verified 500 bug --------------


def test_unhandled_exception_uses_envelope():
    from app.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()

    @app.get("/__boom")
    def _boom():
        raise ValueError("kaboom")

    # No `with` → lifespan/DB startup is skipped; the route raises before any DB use.
    c = TestClient(app, raise_server_exceptions=False)
    resp = c.get("/__boom")
    assert resp.status_code == 500
    assert resp.headers["content-type"].startswith("application/json")
    body = resp.json()
    _assert_envelope(body, 500, "/__boom")
    assert body["error"] == "InternalServerError"


def test_unhandled_exception_hides_detail_in_production(monkeypatch):
    from app.core import config
    from app.main import create_app
    from fastapi.testclient import TestClient

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("CORS_ORIGINS", '["https://app.example.com"]')
    config.get_settings.cache_clear()
    try:
        app = create_app()

        @app.get("/__boom")
        def _boom():
            raise ValueError("secret-trace")

        c = TestClient(app, raise_server_exceptions=False)
        body = c.get("/__boom").json()
        assert body["message"] == "Internal server error"
        assert "secret-trace" not in body["message"]
    finally:
        config.get_settings.cache_clear()


def test_unhandled_exception_is_access_logged(caplog):
    import logging

    from app.main import create_app
    from fastapi.testclient import TestClient

    app = create_app()

    @app.get("/__boom")
    def _boom():
        raise ValueError("kaboom")

    c = TestClient(app, raise_server_exceptions=False)
    # create_app() ran configure_logging() (dictConfig), which replaces the
    # root logger's handlers — including caplog's. Re-attach caplog's handler
    # so the access line emitted on failure is captured.
    logging.getLogger().addHandler(caplog.handler)
    with caplog.at_level(logging.ERROR, logger="app.core.middleware"):
        c.get("/__boom")
    assert any("→ 500" in r.message for r in caplog.records)
