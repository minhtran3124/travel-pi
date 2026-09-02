"""Cross-user access to trips and expenses (#118).

Before this, `trips` had no owner: `list_trips()` returned every live trip and a
guessed UUID reached anyone's itinerary and expenses through either transport.
The tests that matter here are the negative ones — a passing "user A can read
their own trip" proves nothing about the hole that existed.

Two properties are pinned per case:

1. B cannot reach A's trip.
2. B is told **"not found"**, never "forbidden". A distinct forbidden answer
   would confirm to a probe that a guessed id is real.
"""

from __future__ import annotations

import pytest
from app.core.auth import AuthUser, get_current_user
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.db.session import get_session
from app.main import create_app
from fastapi.testclient import TestClient

USER_A = "owner-a"
USER_B = "intruder-b"


def _client_as(tmp_db, user_id: str | None) -> TestClient:
    """A TestClient acting as ``user_id``, or unauthenticated when None."""
    Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)
    seed_all(get_session_factory(tmp_db))
    app = create_app()

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
def a_trip(tmp_db) -> str:
    """A trip owned by USER_A, with one item."""
    with _client_as(tmp_db, USER_A) as c:
        r = c.post("/trips", json={"title": "A's Tokyo trip", "city": "Tokyo"})
        assert r.status_code == 201, r.text
        trip_id = r.json()["id"]
        c.post(
            f"/trips/{trip_id}/items",
            json={"day": 1, "kind": "activity", "title": "Senso-ji"},
        )
    return trip_id


# ---------------------------------------------------------------------------
# Unauthenticated
# ---------------------------------------------------------------------------


def test_unauthenticated_cannot_list_trips(tmp_db):
    with _client_as(tmp_db, None) as c:
        assert c.get("/trips").status_code == 401


def test_unauthenticated_cannot_create_a_trip(tmp_db):
    with _client_as(tmp_db, None) as c:
        assert c.post("/trips", json={"title": "x"}).status_code == 401


# ---------------------------------------------------------------------------
# Another user's trip is invisible, not forbidden
# ---------------------------------------------------------------------------


def test_other_users_trip_is_not_listed(tmp_db, a_trip):
    with _client_as(tmp_db, USER_B) as c:
        body = c.get("/trips").json()
    ids = [t["id"] for t in body["results"]]
    assert a_trip not in ids
    assert ids == [], "B owns nothing, so B's list must be empty"


def test_other_users_trip_reads_as_not_found(tmp_db, a_trip):
    with _client_as(tmp_db, USER_B) as c:
        r = c.get(f"/trips/{a_trip}")
    assert r.status_code == 404, "must not be 403 — that would confirm the id"
    assert "A's Tokyo trip" not in r.text


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("put", "", {"title": "hijacked"}),
        ("delete", "", None),
        ("post", "/items", {"day": 1, "kind": "activity", "title": "intruder item"}),
        ("get", "/budget", None),
        ("get", "/detail", None),
    ],
)
def test_other_user_cannot_touch_the_trip(tmp_db, a_trip, method, path, payload):
    with _client_as(tmp_db, USER_B) as c:
        r = getattr(c, method)(
            f"/trips/{a_trip}{path}", **({"json": payload} if payload else {})
        )
    assert r.status_code == 404, f"{method.upper()} {path} leaked: {r.status_code}"


def test_owner_still_has_full_access(tmp_db, a_trip):
    """The negative tests would also pass if trips were broken for everyone."""
    with _client_as(tmp_db, USER_A) as c:
        assert c.get(f"/trips/{a_trip}").status_code == 200
        # `tmp_db` is session-scoped and the fixture runs per test, so A owns a
        # trip from every earlier case too — membership, not equality.
        assert a_trip in [t["id"] for t in c.get("/trips").json()["results"]]


def test_deleting_another_users_trip_does_not_delete_it(tmp_db, a_trip):
    """A 404 that still performed the write would be the worst outcome."""
    with _client_as(tmp_db, USER_B) as c:
        c.delete(f"/trips/{a_trip}")
    with _client_as(tmp_db, USER_A) as c:
        assert c.get(f"/trips/{a_trip}").status_code == 200, "A's trip was destroyed"


# ---------------------------------------------------------------------------
# Expenses are reached through their trip
# ---------------------------------------------------------------------------


def test_other_user_cannot_add_an_expense_to_the_trip(tmp_db, a_trip):
    with _client_as(tmp_db, USER_B) as c:
        r = c.post(
            "/expenses",
            json={
                "trip_id": a_trip,
                "category": "food",
                "amount": 10,
                "currency": "USD",
                "spent_at": "2026-08-01",
            },
        )
    assert r.status_code == 404


def test_other_user_cannot_list_the_trips_expenses(tmp_db, a_trip):
    with _client_as(tmp_db, USER_A) as c:
        c.post(
            "/expenses",
            json={
                "trip_id": a_trip,
                "category": "food",
                "amount": 10,
                "currency": "USD",
                "spent_at": "2026-08-01",
            },
        )
    with _client_as(tmp_db, USER_B) as c:
        r = c.get("/expenses", params={"trip_id": a_trip})
    assert r.status_code == 404 or r.json().get("results") == []
