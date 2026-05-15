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
