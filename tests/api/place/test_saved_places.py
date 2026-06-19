"""Tests for the saved-places store (crud + service + HTTP) — POI library Wave 1."""

import pytest
from app.schemas.saved_place import SavedPlace


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
    from app.crud.saved_place import SavedPlaceRepository
    from app.db.engine import get_session_factory

    r = SavedPlaceRepository(get_session_factory(f"sqlite:///{tmp_path / 'sp.db'}"))
    r.init_db()
    return r


def test_add_and_get_by_id_and_code(repo):
    sp = repo.add(_make_sp(id="a1", name="Bar"))
    assert repo.get("a1").name == "Bar"
    assert repo.get(sp.short_code).id == "a1"  # SPL- code lookup


def test_soft_delete_filters(repo):
    repo.add(_make_sp(id="a1", name="Bar"))
    assert repo.soft_delete("a1", when="2026-06-18T00:00:00+00:00") is True
    assert repo.get("a1") is None
    assert (
        repo.soft_delete("a1", when="2026-06-18T00:00:00+00:00") is False
    )  # already gone


def test_set_flag(repo):
    repo.add(_make_sp(id="a1", name="Bar"))
    repo.set_flag("a1", "favorite", True)
    assert repo.get("a1").favorite is True


def test_find_duplicate_by_distance(repo):
    repo.add(_make_sp(id="a1", name="Bar", latitude=21.0, longitude=105.8))
    near = repo.find_duplicate(
        name="bar", city=None, lat=21.0001, lng=105.8001, radius_km=0.05
    )
    assert near is not None and near.id == "a1"
    far = repo.find_duplicate(
        name="bar", city=None, lat=22.0, lng=106.0, radius_km=0.05
    )
    assert far is None


def test_find_duplicate_no_coords_uses_city(repo):
    repo.add(_make_sp(id="a1", name="Bar", city="Hanoi"))
    assert repo.find_duplicate(
        name="bar", city="Hanoi", lat=None, lng=None, radius_km=0.05
    )
    assert (
        repo.find_duplicate(name="bar", city="Hue", lat=None, lng=None, radius_km=0.05)
        is None
    )


def test_list_filters_and_order(repo):
    repo.add(_make_sp(id="a1", name="A", city="Hanoi", category="cafe"))
    repo.add(
        _make_sp(id="a2", name="B", city="Hue", category="nightlife", favorite=True)
    )
    assert [s.id for s in repo.list()] == [
        "a2",
        "a1",
    ]  # newest first (created_at desc, then id)
    assert [s.id for s in repo.list(city="Hanoi")] == ["a1"]
    assert [s.id for s in repo.list(category="nightlife")] == ["a2"]
    assert [s.id for s in repo.list(favorite=True)] == ["a2"]


def test_links_round_trip(repo):
    repo.add(_make_sp(id="a1", name="Bar", links=["https://x", "https://y"]))
    assert repo.get("a1").links == ["https://x", "https://y"]


# --------------------------------------------------------------------------- #
# HTTP layer (full app via the shared client fixture)
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
