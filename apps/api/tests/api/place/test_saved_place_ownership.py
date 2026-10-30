"""Cross-user access to saved places: user B must not read, delete, favourite, mark-visited, or list user A's saved place — always 404, never 403."""

from __future__ import annotations

import uuid

import pytest
from app.core.auth import AuthUser, get_current_user
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.session import get_session
from fastapi.testclient import TestClient

from tests.fixtures.light_app import create_app_without_lifespan, ensure_seeded

USER_A = "owner-a"
USER_B = "intruder-b"


def _client_as(tmp_db, user_id: str | None) -> TestClient:
    """A TestClient acting as ``user_id``, or unauthenticated when None."""
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)
    ensure_seeded(tmp_db)
    app = create_app_without_lifespan()

    def _session():
        s = get_session_factory(tmp_db)()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[get_session] = _session
    if user_id is not None:
        app.dependency_overrides[get_current_user] = lambda: AuthUser(
            id=user_id, email=f"{user_id}@test", role=None, claims={}
        )
    return TestClient(app)


@pytest.fixture()
def a_saved_place(tmp_db) -> str:
    """A saved place owned by USER_A (unique name: tmp_db is session-scoped and creation dedups on name+proximity)."""
    with _client_as(tmp_db, USER_A) as c:
        r = c.post(
            "/places/saved",
            json={
                "name": f"A's Secret Cafe {uuid.uuid4().hex[:8]}",
                "city": "Da Nang",
                "category": "cafe",
                "lat": 16.0678,
                "lng": 108.2208,
            },
        )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Unauthenticated → 401
# ---------------------------------------------------------------------------


def test_unauthenticated_cannot_list_saved_places(tmp_db):
    with _client_as(tmp_db, None) as c:
        assert c.get("/places/saved").status_code == 401


def test_unauthenticated_cannot_create_a_saved_place(tmp_db):
    with _client_as(tmp_db, None) as c:
        r = c.post("/places/saved", json={"name": "x", "city": "Da Nang"})
    assert r.status_code == 401


def test_unauthenticated_cannot_read_a_saved_place(tmp_db, a_saved_place):
    with _client_as(tmp_db, None) as c:
        assert c.get(f"/places/saved/{a_saved_place}").status_code == 401


# ---------------------------------------------------------------------------
# Another user's saved place is invisible, not forbidden
# ---------------------------------------------------------------------------


def test_other_users_saved_place_is_not_listed(tmp_db, a_saved_place):
    with _client_as(tmp_db, USER_B) as c:
        body = c.get("/places/saved", params={"limit": 500}).json()
    ids = [p["id"] for p in body["results"]]
    assert a_saved_place not in ids
    assert ids == [], "B owns no saved places, so B's list must be empty"


def test_other_user_cannot_read_the_saved_place(tmp_db, a_saved_place):
    with _client_as(tmp_db, USER_B) as c:
        r = c.get(f"/places/saved/{a_saved_place}")
    assert r.status_code == 404, "must not be 403 — that would confirm the id"
    assert "A's Secret Cafe" not in r.text


def test_other_user_cannot_favorite_the_saved_place(tmp_db, a_saved_place):
    with _client_as(tmp_db, USER_B) as c:
        r = c.post(f"/places/saved/{a_saved_place}/favorite", json={"value": True})
    assert r.status_code == 404


def test_other_user_cannot_mark_the_saved_place_visited(tmp_db, a_saved_place):
    with _client_as(tmp_db, USER_B) as c:
        r = c.post(f"/places/saved/{a_saved_place}/visited", json={"value": True})
    assert r.status_code == 404


def test_other_user_cannot_delete_the_saved_place(tmp_db, a_saved_place):
    with _client_as(tmp_db, USER_B) as c:
        r = c.delete(f"/places/saved/{a_saved_place}")
    assert r.status_code == 404


def test_other_user_delete_does_not_actually_delete(tmp_db, a_saved_place):
    """A 404 that still performed the soft-delete would be the worst outcome."""
    with _client_as(tmp_db, USER_B) as c:
        c.delete(f"/places/saved/{a_saved_place}")
    with _client_as(tmp_db, USER_A) as c:
        assert c.get(f"/places/saved/{a_saved_place}").status_code == 200, (
            "A's saved place was destroyed by B"
        )


# ---------------------------------------------------------------------------
# Owner keeps full access (guards against "broken for everyone")
# ---------------------------------------------------------------------------


def test_owner_can_read_and_list_their_saved_place(tmp_db, a_saved_place):
    with _client_as(tmp_db, USER_A) as c:
        assert c.get(f"/places/saved/{a_saved_place}").status_code == 200
        ids = [
            p["id"]
            for p in c.get("/places/saved", params={"limit": 500}).json()["results"]
        ]
    assert a_saved_place in ids
