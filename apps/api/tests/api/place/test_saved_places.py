"""Saved-places store (crud + service + HTTP): per-user, repo filters on user_id and the ``/places/saved*`` routes require a signed-in caller."""

import uuid

import pytest
from app.core.auth import AuthUser, get_current_user
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.session import get_session
from app.schemas.saved_place import SavedPlace
from fastapi.testclient import TestClient

from tests.fixtures.light_app import create_app_without_lifespan, ensure_seeded

USER = "sp-owner"


def _make_sp(**over) -> SavedPlace:
    """Build a full SavedPlace (id + created_at populated) for repo.add()."""
    base = {
        "id": "sp-1",
        "created_at": "2026-06-18T00:00:00+00:00",
        "name": "Place",
    }
    base.update(over)
    return SavedPlace(**base)


# --------------------------------------------------------------------------- #
# CRUD layer (direct SavedPlaceRepository against a temp DB)
# --------------------------------------------------------------------------- #


@pytest.fixture()
def repo(tmp_path):
    from app.db.engine import get_session_factory
    from app.repositories.saved_place import SavedPlaceRepository

    r = SavedPlaceRepository(get_session_factory(f"sqlite:///{tmp_path / 'sp.db'}"))
    r.init_db()
    return r


def test_add_and_get_by_id_and_code(repo):
    sp = repo.add(_make_sp(id="a1", name="Bar"), USER)
    assert repo.get("a1", USER).name == "Bar"
    assert repo.get(sp.short_code, USER).id == "a1"


def test_soft_delete_filters(repo):
    repo.add(_make_sp(id="a1", name="Bar"), USER)
    assert repo.soft_delete("a1", USER, when="2026-06-18T00:00:00+00:00") is True
    assert repo.get("a1", USER) is None
    assert (
        repo.soft_delete("a1", USER, when="2026-06-18T00:00:00+00:00") is False
    )  # already gone


def test_set_flag(repo):
    repo.add(_make_sp(id="a1", name="Bar"), USER)
    repo.set_flag("a1", USER, "favorite", True)
    assert repo.get("a1", USER).favorite is True


def test_find_duplicate_by_distance(repo):
    repo.add(_make_sp(id="a1", name="Bar", latitude=21.0, longitude=105.8), USER)
    near = repo.find_duplicate(
        user_id=USER, name="bar", city=None, lat=21.0001, lng=105.8001, radius_km=0.05
    )
    assert near is not None and near.id == "a1"
    far = repo.find_duplicate(
        user_id=USER, name="bar", city=None, lat=22.0, lng=106.0, radius_km=0.05
    )
    assert far is None


def test_find_duplicate_no_coords_uses_city(repo):
    repo.add(_make_sp(id="a1", name="Bar", city="Hanoi"), USER)
    assert repo.find_duplicate(
        user_id=USER, name="bar", city="Hanoi", lat=None, lng=None, radius_km=0.05
    )
    assert (
        repo.find_duplicate(
            user_id=USER, name="bar", city="Hue", lat=None, lng=None, radius_km=0.05
        )
        is None
    )


def test_list_filters_and_order(repo):
    repo.add(_make_sp(id="a1", name="A", city="Hanoi", category="cafe"), USER)
    repo.add(
        _make_sp(id="a2", name="B", city="Hue", category="nightlife", favorite=True),
        USER,
    )
    assert [s.id for s in repo.list(USER)] == [
        "a2",
        "a1",
    ]  # newest first (created_at desc, then id)
    assert [s.id for s in repo.list(USER, city="Hanoi")] == ["a1"]
    assert [s.id for s in repo.list(USER, category="nightlife")] == ["a2"]
    assert [s.id for s in repo.list(USER, favorite=True)] == ["a2"]


def test_links_round_trip(repo):
    repo.add(_make_sp(id="a1", name="Bar", links=["https://x", "https://y"]), USER)
    assert repo.get("a1", USER).links == ["https://x", "https://y"]


def test_repo_is_owner_scoped(repo):
    """A row stamped for one owner is invisible to another."""
    repo.add(_make_sp(id="a1", name="Bar"), "owner-a")
    assert repo.get("a1", "owner-b") is None
    assert repo.list("owner-b") == []
    assert repo.soft_delete("a1", "owner-b", when="2026-06-18T00:00:00+00:00") is False
    assert repo.set_flag("a1", "owner-b", "favorite", True) is False
    # owner-b's create is not blocked by owner-a's same-name row
    assert (
        repo.find_duplicate(
            user_id="owner-b", name="Bar", city=None, lat=None, lng=None, radius_km=0.05
        )
        is None
    )
    # owner-a still sees their own row untouched
    assert repo.get("a1", "owner-a").favorite is False


# --------------------------------------------------------------------------- #
# HTTP layer (full app via the shared client fixture — authenticated as the
# default test traveller by tests/conftest.py)
# --------------------------------------------------------------------------- #


def test_create_get_list_saved(client):
    r = client.post(
        "/places/saved",
        json={"name": "Rooftop", "city": "Hanoi", "category": "nightlife"},
    )
    assert r.status_code == 201
    sid = r.json()["id"]
    assert client.get(f"/places/saved/{sid}").status_code == 200
    assert any(p["id"] == sid for p in client.get("/places/saved").json()["results"])


def test_dedup_conflict(client):
    body = {"name": "Twin", "latitude": 21.0, "longitude": 105.8}
    assert client.post("/places/saved", json=body).status_code == 201
    assert (
        client.post(
            "/places/saved",
            json={**body, "latitude": 21.0001, "longitude": 105.8001},
        ).status_code
        == 409
    )


def test_favorite_set_idempotent(client):
    sid = client.post("/places/saved", json={"name": "X"}).json()["id"]
    for _ in range(2):
        r = client.post(f"/places/saved/{sid}/favorite", json={"value": True})
        assert r.status_code == 200 and r.json()["favorite"] is True


def test_soft_delete_saved(client):
    sid = client.post("/places/saved", json={"name": "Y"}).json()["id"]
    assert client.delete(f"/places/saved/{sid}").status_code == 204
    assert client.get(f"/places/saved/{sid}").status_code == 404


def test_flag_and_delete_by_short_code(client):
    # SPL- short code must work for set-flag and delete, not just the UUID.
    created = client.post("/places/saved", json={"name": "ByCode"}).json()
    code = created["short_code"]
    r = client.post(f"/places/saved/{code}/favorite", json={"value": True})
    assert r.status_code == 200 and r.json()["favorite"] is True
    # the change actually persisted (re-fetch by UUID)
    assert client.get(f"/places/saved/{created['id']}").json()["favorite"] is True
    assert client.delete(f"/places/saved/{code}").status_code == 204
    assert client.get(f"/places/saved/{created['id']}").status_code == 404


# --------------------------------------------------------------------------- #
# Auth + cross-user isolation: B gets 404 (never 403, which confirms an id);
# public catalog routes stay open to anonymous callers.
# --------------------------------------------------------------------------- #

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
def a_saved(tmp_db) -> str:
    """A saved place owned by USER_A (unique name: tmp_db is session-scoped and the dedup guard is per-owner)."""
    name = f"A's secret bar {uuid.uuid4()}"
    with _client_as(tmp_db, USER_A) as c:
        r = c.post("/places/saved", json={"name": name, "city": "Hanoi"})
        assert r.status_code == 201, r.text
        return r.json()["id"]


def test_unauthenticated_cannot_create_saved(tmp_db):
    with _client_as(tmp_db, None) as c:
        assert c.post("/places/saved", json={"name": "x"}).status_code == 401


def test_unauthenticated_cannot_list_saved(tmp_db):
    with _client_as(tmp_db, None) as c:
        assert c.get("/places/saved").status_code == 401


def test_other_users_saved_is_not_listed(tmp_db, a_saved):
    with _client_as(tmp_db, USER_B) as c:
        ids = [p["id"] for p in c.get("/places/saved").json()["results"]]
    assert a_saved not in ids
    assert ids == [], "B owns nothing, so B's list must be empty"


def test_other_users_saved_reads_as_not_found(tmp_db, a_saved):
    with _client_as(tmp_db, USER_B) as c:
        r = c.get(f"/places/saved/{a_saved}")
    assert r.status_code == 404, "must not be 403 — that would confirm the id"
    assert "A's secret bar" not in r.text


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("delete", "", None),
        ("post", "/favorite", {"value": True}),
        ("post", "/visited", {"value": True}),
    ],
)
def test_other_user_cannot_touch_saved(tmp_db, a_saved, method, path, payload):
    with _client_as(tmp_db, USER_B) as c:
        r = getattr(c, method)(
            f"/places/saved/{a_saved}{path}", **({"json": payload} if payload else {})
        )
    assert r.status_code == 404, f"{method.upper()} {path} leaked: {r.status_code}"


def test_deleting_another_users_saved_does_not_delete_it(tmp_db, a_saved):
    """A 404 that still performed the write would be the worst outcome."""
    with _client_as(tmp_db, USER_B) as c:
        c.delete(f"/places/saved/{a_saved}")
    with _client_as(tmp_db, USER_A) as c:
        assert c.get(f"/places/saved/{a_saved}").status_code == 200, "A's row destroyed"


def test_owner_still_has_full_access(tmp_db, a_saved):
    """The negative tests would also pass if saved places were broken for all."""
    with _client_as(tmp_db, USER_A) as c:
        assert c.get(f"/places/saved/{a_saved}").status_code == 200
        assert a_saved in [p["id"] for p in c.get("/places/saved").json()["results"]]


def test_public_catalog_routes_stay_open(tmp_db):
    """The read-only catalog surface must not require a token."""
    with _client_as(tmp_db, None) as c:
        assert c.get("/places/search", params={"city": "Hanoi"}).status_code == 200
        assert c.get("/places/cities").status_code == 200
        assert c.get("/places/categories").status_code == 200
