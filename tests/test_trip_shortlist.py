"""HTTP tests for the trip shortlist (Wave 2 — resolver + trip_place_link)."""


def _trip(client):
    return client.post("/trips", json={"title": "T", "travelers": 1}).json()["id"]


def test_add_catalog_place_to_trip(client):
    tid = _trip(client)
    pid = client.get("/places", params={"limit": 1}).json()["results"][0]["id"]
    r = client.post(f"/trips/{tid}/places", json={"place_id": pid, "source": "catalog"})
    assert r.status_code == 201 and r.json()["source"] == "catalog"
    lst = client.get(f"/trips/{tid}/places").json()
    assert len(lst) == 1 and lst[0]["place"]["id"] == pid
    # additive on TripDetail
    assert client.get(f"/trips/{tid}").json()["places"][0]["place"]["id"] == pid


def test_add_saved_place_and_dedupe_409(client):
    tid = _trip(client)
    sid = client.post("/places/saved", json={"name": "S"}).json()["id"]
    body = {"place_id": sid, "source": "saved"}
    first = client.post(f"/trips/{tid}/places", json=body)
    assert first.status_code == 201
    assert (
        client.post(f"/trips/{tid}/places", json=body).status_code == 409
    )  # duplicate


def test_unknown_place_404_and_remove(client):
    tid = _trip(client)
    assert (
        client.post(
            f"/trips/{tid}/places", json={"place_id": "nope", "source": "catalog"}
        ).status_code
        == 404
    )
    pid = client.get("/places", params={"limit": 1}).json()["results"][0]["id"]
    link_id = client.post(f"/trips/{tid}/places", json={"place_id": pid}).json()[
        "link_id"
    ]
    assert client.delete(f"/trips/{tid}/places/{link_id}").status_code == 204
    assert client.get(f"/trips/{tid}/places").json() == []


def test_default_source_is_catalog(client):
    tid = _trip(client)
    pid = client.get("/places", params={"limit": 1}).json()["results"][0]["id"]
    r = client.post(f"/trips/{tid}/places", json={"place_id": pid})
    assert r.status_code == 201 and r.json()["source"] == "catalog"


def test_invalid_source_422(client):
    tid = _trip(client)
    r = client.post(f"/trips/{tid}/places", json={"place_id": "x", "source": "bogus"})
    assert r.status_code == 422


def test_add_place_unknown_trip_404(client):
    pid = client.get("/places", params={"limit": 1}).json()["results"][0]["id"]
    r = client.post("/trips/nope/places", json={"place_id": pid, "source": "catalog"})
    assert r.status_code == 404


def test_remove_unknown_link_404(client):
    tid = _trip(client)
    assert client.delete(f"/trips/{tid}/places/nope").status_code == 404


def test_deleted_saved_place_dropped_from_shortlist(client):
    tid = _trip(client)
    sid = client.post("/places/saved", json={"name": "Ghost"}).json()["id"]
    assert (
        client.post(
            f"/trips/{tid}/places", json={"place_id": sid, "source": "saved"}
        ).status_code
        == 201
    )
    # Soft-delete the saved place; the shortlist entry no longer resolves.
    assert client.delete(f"/places/saved/{sid}").status_code == 204
    assert client.get(f"/trips/{tid}/places").json() == []
