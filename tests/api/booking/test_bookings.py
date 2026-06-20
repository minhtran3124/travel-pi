"""Tests for booking endpoints: list (paginated) and detail."""

import pytest
from app.services import hotel_service

from tests.conftest import (
    VALID_CHECK_IN,
    VALID_CHECK_OUT,
    get_first_flight_booking_fields,
    get_first_hotel_id,
)


@pytest.fixture(autouse=True)
def _rooms_always_available(monkeypatch):
    """Pin hotel availability high so hotel bookings here always succeed."""
    monkeypatch.setattr(hotel_service, "available_rooms", lambda *a, **k: 99)


def _create_flight_booking(client, name="Test User", email="test@example.com"):
    return client.post(
        "/flights/book",
        json={
            **get_first_flight_booking_fields(client),
            "passenger_name": name,
            "passenger_email": email,
            "passenger_phone": "+84 901 234 567",
        },
    ).json()


def _create_hotel_booking(client, name="Test User", email="test@example.com"):
    hotel_id = get_first_hotel_id(client)
    return client.post(
        "/hotels/book",
        json={
            "hotel_id": hotel_id,
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "guests": 1,
            "guest_name": name,
            "guest_email": email,
            "guest_phone": "+84 901 234 567",
        },
    ).json()


def _all_bookings(client, **params):
    """Fetch all bookings by using a large limit."""
    return client.get("/bookings", params={"limit": 500, **params}).json()["results"]


# ---------------------------------------------------------------------------
# GET /bookings  (paginated)
# ---------------------------------------------------------------------------


def test_list_bookings_returns_200(client):
    assert client.get("/bookings").status_code == 200


def test_list_bookings_returns_paginated_envelope(client):
    body = client.get("/bookings").json()
    for field in ("total", "limit", "offset", "results"):
        assert field in body
    assert isinstance(body["results"], list)


def test_list_bookings_default_limit(client):
    body = client.get("/bookings").json()
    assert body["limit"] == 20
    assert body["offset"] == 0


def test_list_bookings_custom_limit(client):
    body = client.get("/bookings", params={"limit": 3}).json()
    assert body["limit"] == 3
    assert len(body["results"]) <= 3


def test_list_bookings_limit_validation(client):
    assert client.get("/bookings", params={"limit": 0}).status_code == 422
    assert client.get("/bookings", params={"limit": 501}).status_code == 422


def test_list_bookings_offset_validation(client):
    assert client.get("/bookings", params={"offset": -1}).status_code == 422


def test_list_bookings_contains_created_bookings(client):
    booking = _create_flight_booking(client, "ListUser", "listuser@example.com")
    ids = [b["id"] for b in _all_bookings(client)]
    assert booking["id"] in ids


def test_list_bookings_filter_by_type_flight(client):
    _create_flight_booking(client, "FlightFilter", "flightfilter@example.com")
    results = _all_bookings(client, type="flight")
    assert all(b["type"] == "flight" for b in results)


def test_list_bookings_filter_by_type_hotel(client):
    _create_hotel_booking(client, "HotelFilter", "hotelfilter@example.com")
    results = _all_bookings(client, type="hotel")
    assert all(b["type"] == "hotel" for b in results)


def test_list_bookings_unknown_type_returns_422(client):
    """``type`` is a BookingType enum — an unknown value is now 422 instead of
    being silently dropped."""
    resp = client.get("/bookings", params={"type": "unknown"})
    assert resp.status_code == 422


def test_list_bookings_search_by_name(client):
    unique_name = "UniqueNameXYZ987"
    booking = _create_flight_booking(client, unique_name, "unique987@example.com")
    results = _all_bookings(client, q=unique_name)
    assert len(results) >= 1
    assert any(b["id"] == booking["id"] for b in results)


def test_list_bookings_search_by_email(client):
    unique_email = "veryrandom123abc@example.com"
    booking = _create_hotel_booking(client, "Random User", unique_email)
    results = _all_bookings(client, q=unique_email)
    assert any(b["id"] == booking["id"] for b in results)


def test_list_bookings_search_case_insensitive(client):
    unique_name = "CaseSensTest"
    booking = _create_flight_booking(client, unique_name, "casetest@example.com")
    results = _all_bookings(client, q=unique_name.lower())
    assert any(b["id"] == booking["id"] for b in results)


def test_list_bookings_sort_price_asc(client):
    results = _all_bookings(client, sort="price_asc")
    if len(results) > 1:
        prices = [b["total_price"] for b in results]
        assert prices == sorted(prices)


def test_list_bookings_sort_price_desc(client):
    results = _all_bookings(client, sort="price_desc")
    if len(results) > 1:
        prices = [b["total_price"] for b in results]
        assert prices == sorted(prices, reverse=True)


def test_list_bookings_sort_created_asc(client):
    results = _all_bookings(client, sort="created_asc")
    if len(results) > 1:
        dates = [b["created_at"] for b in results]
        assert dates == sorted(dates)


def test_list_bookings_sort_created_desc(client):
    results = _all_bookings(client, sort="created_desc")
    if len(results) > 1:
        dates = [b["created_at"] for b in results]
        assert dates == sorted(dates, reverse=True)


def test_list_bookings_booking_has_required_fields(client):
    _create_flight_booking(client)
    bookings = _all_bookings(client)
    assert len(bookings) > 0
    booking = bookings[0]
    for field in (
        "id",
        "type",
        "reference_id",
        "customer_name",
        "customer_email",
        "total_price",
        "currency",
        "status",
        "created_at",
        "details",
    ):
        assert field in booking


def test_list_bookings_pagination_offset(client):
    _create_flight_booking(client, "PagA", "paga@example.com")
    _create_flight_booking(client, "PagB", "pagb@example.com")
    total = client.get("/bookings").json()["total"]
    if total > 1:
        r1 = client.get("/bookings", params={"limit": 1, "offset": 0}).json()
        r2 = client.get("/bookings", params={"limit": 1, "offset": 1}).json()
        assert r1["total"] == total
        assert r2["total"] == total
        assert r1["results"][0]["id"] != r2["results"][0]["id"]


def test_list_bookings_total_stable_across_pages(client):
    t1 = client.get("/bookings", params={"limit": 2, "offset": 0}).json()["total"]
    t2 = client.get("/bookings", params={"limit": 2, "offset": 2}).json()["total"]
    assert t1 == t2


# ---------------------------------------------------------------------------
# GET /bookings/{booking_id}
# ---------------------------------------------------------------------------


def test_get_booking_returns_200(client):
    booking = _create_flight_booking(client, "GetUser", "getuser@example.com")
    assert client.get(f"/bookings/{booking['id']}").status_code == 200


def test_get_booking_returns_correct_data(client):
    booking = _create_flight_booking(client, "DetailUser", "detail@example.com")
    body = client.get(f"/bookings/{booking['id']}").json()
    assert body["id"] == booking["id"]
    assert body["customer_name"] == "DetailUser"
    assert body["customer_email"] == "detail@example.com"


def test_get_booking_nonexistent_returns_404(client):
    assert (
        client.get("/bookings/00000000-0000-0000-0000-000000000000").status_code == 404
    )


def test_get_hotel_booking_by_id(client):
    booking = _create_hotel_booking(client, "HotelGetUser", "hotelget@example.com")
    body = client.get(f"/bookings/{booking['id']}").json()
    assert body["id"] == booking["id"]
    assert body["type"] == "hotel"


# ---------------------------------------------------------------------------
# Confirmation code + summary (friendly identifiers)
# ---------------------------------------------------------------------------

_CODE_ALPHABET = set("ABCDEFGHJKMNPQRSTUVWXYZ23456789")


def test_booking_has_confirmation_code(client):
    booking = _create_flight_booking(client, "CodeUser", "code@example.com")
    code = booking["confirmation_code"]
    assert len(code) == 6
    assert set(code) <= _CODE_ALPHABET


def test_confirmation_code_is_stable_for_same_booking(client):
    booking = _create_hotel_booking(client, "StableUser", "stable@example.com")
    refetched = client.get(f"/bookings/{booking['id']}").json()
    assert refetched["confirmation_code"] == booking["confirmation_code"]


def test_booking_has_human_readable_summary(client):
    flight = _create_flight_booking(client, "SummaryUser", "summary@example.com")
    assert "SummaryUser" in flight["summary"]
    assert "→" in flight["summary"]
    hotel = _create_hotel_booking(client, "HotelSummary", "hsummary@example.com")
    assert "HotelSummary" in hotel["summary"]
    assert "night" in hotel["summary"]


def test_get_booking_by_confirmation_code(client):
    booking = _create_flight_booking(client, "ByCodeUser", "bycode@example.com")
    body = client.get(f"/bookings/{booking['confirmation_code']}").json()
    assert body["id"] == booking["id"]


def test_get_booking_by_confirmation_code_case_insensitive(client):
    booking = _create_hotel_booking(client, "LowerCode", "lowercode@example.com")
    code = booking["confirmation_code"].lower()
    body = client.get(f"/bookings/{code}").json()
    assert body["id"] == booking["id"]


def test_get_booking_unknown_confirmation_code_returns_404(client):
    assert client.get("/bookings/ZZZZZZ").status_code == 404


def test_search_bookings_by_confirmation_code(client):
    booking = _create_flight_booking(client, "SearchCode", "searchcode@example.com")
    results = _all_bookings(client, q=booking["confirmation_code"])
    assert any(b["id"] == booking["id"] for b in results)


# ---------------------------------------------------------------------------
# POST /bookings/{id}/cancel
# ---------------------------------------------------------------------------


def test_cancel_booking_sets_status_cancelled(client):
    booking = _create_flight_booking(client, "CancelMe", "cancelme@example.com")
    body = client.post(f"/bookings/{booking['id']}/cancel").json()
    assert body["status"] == "cancelled"
    assert body["id"] == booking["id"]


def test_cancel_booking_persists(client):
    booking = _create_hotel_booking(client, "CancelPersist", "cp@example.com")
    client.post(f"/bookings/{booking['id']}/cancel")
    assert client.get(f"/bookings/{booking['id']}").json()["status"] == "cancelled"


def test_cancel_booking_by_confirmation_code(client):
    booking = _create_flight_booking(client, "CancelByCode", "cbc@example.com")
    body = client.post(f"/bookings/{booking['confirmation_code']}/cancel").json()
    assert body["status"] == "cancelled"
    assert body["id"] == booking["id"]


def test_cancel_booking_is_idempotent(client):
    booking = _create_flight_booking(client, "CancelTwice", "ct@example.com")
    first = client.post(f"/bookings/{booking['id']}/cancel").json()
    second = client.post(f"/bookings/{booking['id']}/cancel").json()
    assert first["status"] == second["status"] == "cancelled"


def test_cancel_unknown_booking_returns_404(client):
    assert (
        client.post("/bookings/00000000-0000-0000-0000-000000000000/cancel").status_code
        == 404
    )


# ---------------------------------------------------------------------------
# Idempotency-key uniqueness (data layer)
# ---------------------------------------------------------------------------


def _sample_booking(booking_id):
    from datetime import datetime, timezone

    from app.enums import BookingType
    from app.schemas.booking import Booking, FlightBookingDetails

    return Booking(
        id=booking_id,
        type=BookingType.FLIGHT,
        reference_id="ref-1",
        customer_name="Race Tester",
        customer_email="race@example.com",
        total_price=100.0,
        created_at=datetime.now(timezone.utc),
        details=FlightBookingDetails(
            flight_id="ref-1",
            flight_number="VN123",
            airline="Vietnam Airlines",
            origin="DAD",
            destination="SGN",
            departure_time="2026-06-01T08:30:00",
            arrival_time="2026-06-01T10:00:00",
            passenger_name="Race Tester",
        ),
    )


def test_repo_add_duplicate_idempotency_key_returns_winner(tmp_db):
    """A second add() under an already-used idempotency key must not create a
    duplicate row — it returns the booking the first add() created."""
    from app.db.engine import get_session_factory
    from app.repositories.booking import BookingRepository

    repo = BookingRepository(get_session_factory(tmp_db))
    repo.init_db()

    first = repo.add(
        _sample_booking("11111111-1111-1111-1111-111111111111"), "race-key"
    )
    second = repo.add(
        _sample_booking("22222222-2222-2222-2222-222222222222"), "race-key"
    )

    # The loser's INSERT hit the UNIQUE index and we got the winner back instead.
    assert second.id == first.id
    assert repo.get("22222222-2222-2222-2222-222222222222") is None


# ---------------------------------------------------------------------------
# Confirmation-code lookup (indexed column, no full-table scan)
# ---------------------------------------------------------------------------


def test_repo_get_by_confirmation_code_resolves(tmp_db):
    """The new indexed lookup returns the same booking the original add stored."""
    from app.db.engine import get_engine, get_session_factory
    from app.repositories.booking import BookingRepository
    from sqlalchemy import inspect

    # Use the shared per-session test DB URL directly. (Don't fabricate a
    # sibling URL by string-appending — that yields a valid distinct SQLite
    # file but an invalid/non-existent Postgres database name, which breaks the
    # docker-compose.test.yml Postgres parity run.)
    url = tmp_db
    repo = BookingRepository(get_session_factory(url))
    repo.init_db()
    booking = repo.add(_sample_booking("33333333-3333-3333-3333-333333333333"))

    found = repo.get_by_confirmation_code(booking.confirmation_code)
    assert found is not None and found.id == booking.id
    # Case-insensitive: the helper upper-cases the input before the lookup.
    assert (
        repo.get_by_confirmation_code(booking.confirmation_code.lower()).id
        == booking.id
    )
    # The index actually exists on disk.
    names = {i["name"] for i in inspect(get_engine(url)).get_indexes("bookings")}
    assert "ix_bookings_confirmation_code" in names


# ---------------------------------------------------------------------------
# Confirmation-code uniqueness (collision-safe minting + UNIQUE index)
# ---------------------------------------------------------------------------


def test_mint_booking_id_retries_past_confirmation_code_collision(
    client, booking_service, monkeypatch
):
    """A minted UUID whose derived confirmation_code already exists is regenerated.

    Force the first candidate ID to collide with an existing booking's code; the
    minter must skip it and return the next, collision-free candidate.
    """
    from app.services import booking_service as booking_module

    existing = _create_flight_booking(client, "Collide", "collide@example.com")
    fresh_id = "0a111111-2222-3333-4444-555555555555"
    candidates = iter([existing["id"], fresh_id])  # first collides, second is free
    monkeypatch.setattr(booking_module, "_new_booking_id", lambda: next(candidates))

    assert booking_service._mint_booking_id() == fresh_id


def test_duplicate_confirmation_code_rejected_by_unique_index(booking_service, tmp_db):
    """The DB-level UNIQUE index rejects a second row with the same code.

    Uses flush + rollback so nothing is committed to the shared session DB.
    """
    from app.db import models
    from app.db.engine import get_session_factory
    from sqlalchemy.exc import IntegrityError

    def _row(booking_id):
        return models.Booking(
            id=booking_id,
            type="flight",
            reference_id="ref",
            customer_name="Dup",
            customer_email="dup@example.com",
            total_price=1.0,
            currency="USD",
            status="confirmed",
            details={},
            confirmation_code="ZZTEST",
        )

    sf = get_session_factory(tmp_db)
    with sf() as s:
        s.add(_row("dup-id-1"))
        s.flush()
        s.add(_row("dup-id-2"))
        with pytest.raises(IntegrityError):
            s.flush()
        s.rollback()
