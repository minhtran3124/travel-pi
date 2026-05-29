"""End-to-end workflow tests — full agent journeys across endpoints.

The rest of the suite tests endpoints in isolation. These exercise the
realistic multi-step flows an agent actually performs (search → book → list →
cancel; plan a trip end to end), which is the class of cross-endpoint /
cross-schema coupling a single-endpoint test can miss.
"""

import pytest
from app.exceptions import WeatherUnavailableError
from app.services import hotel_service, weather_service

from tests.conftest import (
    VALID_CHECK_IN,
    VALID_CHECK_OUT,
    VALID_DATE,
    VALID_DESTINATION,
    VALID_ORIGIN,
    get_first_flight_booking_fields,
    get_first_hotel_id,
)


@pytest.fixture(autouse=True)
def _rooms_always_available(monkeypatch):
    monkeypatch.setattr(hotel_service, "available_rooms", lambda *a, **k: 99)


@pytest.fixture(autouse=True)
def _no_live_weather(monkeypatch):
    """Keep the suite network-free: the overview's weather call degrades to None.

    The overview is best-effort about weather, so forcing the upstream to fail
    exercises that path while never touching the network.
    """

    async def boom(city, days=None):
        raise WeatherUnavailableError("stubbed offline in tests")

    monkeypatch.setattr(weather_service, "get_weather", boom)


def test_flight_search_book_retrieve_cancel(client):
    """Search a flight, book it, find it in the ledger, then cancel it."""
    # 1. Search.
    results = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
        },
    ).json()["results"]
    assert results
    flight = results[0]

    # 2. Book.
    booking = client.post(
        "/flights/book",
        json={
            "flight_number": flight["flight_number"],
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
            "passenger_name": "E2E Flyer",
            "passenger_email": "e2e@example.com",
            "passenger_phone": "+84 901 234 567",
        },
    ).json()
    assert booking["status"] == "confirmed"
    assert booking["total_price"] == flight["price"]
    booking_id = booking["id"]
    code = booking["confirmation_code"]

    # 3. Retrieve by confirmation code, and find it via search.
    assert client.get(f"/bookings/{code}").json()["id"] == booking_id
    found = client.get("/bookings", params={"q": "E2E Flyer", "limit": 500}).json()
    assert any(b["id"] == booking_id for b in found["results"])

    # 4. Cancel (idempotent).
    assert client.post(f"/bookings/{booking_id}/cancel").json()["status"] == "cancelled"
    assert client.post(f"/bookings/{booking_id}/cancel").json()["status"] == "cancelled"


def test_hotel_availability_book_then_appears_in_ledger(client):
    """Check availability, book a hotel, confirm it shows up in /bookings."""
    avail = client.get(
        "/hotels/availability",
        params={
            "city": "Da Nang",
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
        },
    ).json()["results"]
    assert avail
    hotel = avail[0]

    booking = client.post(
        "/hotels/book",
        json={
            "hotel_id": hotel["id"],
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "rooms": 1,
            "adults": 2,
            "guest_name": "E2E Guest",
            "guest_email": "guest@example.com",
            "guest_phone": "+84 901 234 567",
        },
    ).json()
    assert booking["type"] == "hotel"
    # total_price computed server-side: price_per_night * nights * rooms.
    assert booking["total_price"] == pytest.approx(hotel["price_per_night"] * 2)
    assert client.get(f"/bookings/{booking['id']}").status_code == 200


def test_plan_full_trip_end_to_end(client):
    """The headline agent flow: research a city, book, assemble a trip, amend it."""
    # 1. Research the destination in one call (weather stubbed offline).
    overview = client.get("/destinations/Da Nang/overview")
    assert overview.status_code == 200
    city = overview.json()["city"]
    assert city == "Da Nang"

    # 2. Book a flight and a hotel for it.
    flight_booking = client.post(
        "/flights/book",
        json={
            **get_first_flight_booking_fields(client),
            "passenger_name": "Planner",
            "passenger_email": "planner@example.com",
            "passenger_phone": "+84 901 234 567",
        },
    ).json()["id"]
    hotel_booking = client.post(
        "/hotels/book",
        json={
            "hotel_id": get_first_hotel_id(client),
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "adults": 2,
            "guest_name": "Planner",
            "guest_email": "planner@example.com",
            "guest_phone": "+84 901 234 567",
        },
    ).json()["id"]

    # 3. Pick a couple of places for the itinerary.
    places = client.get("/places/search", params={"city": city}).json()["results"]
    assert len(places) >= 2

    # 4. Assemble the trip.
    trip = client.post(
        "/trips",
        json={
            "name": "Da Nang adventure",
            "destination_city": city,
            "start_date": VALID_CHECK_IN,
            "end_date": VALID_CHECK_OUT,
            "booking_ids": [flight_booking, hotel_booking],
            "items": [
                {"place_id": places[0]["id"], "day": 1},
                {"place_id": places[1]["id"], "day": 2},
            ],
        },
    ).json()
    trip_id = trip["id"]
    assert trip["nights"] == 2
    assert len(trip["booking_ids"]) == 2

    # 5. Fetch the expanded trip — bookings and places resolved in one call.
    detail = client.get(f"/trips/{trip_id}").json()
    assert {b["id"] for b in detail["bookings"]} == {flight_booking, hotel_booking}
    assert len(detail["itinerary"]) == 2
    assert detail["itinerary"][0]["place"]["city"] == "Da Nang"

    # 6. Amend: mark booked, drop one itinerary stop.
    amended = client.patch(
        f"/trips/{trip_id}",
        json={"status": "booked", "items": [{"place_id": places[0]["id"], "day": 1}]},
    ).json()
    assert amended["status"] == "booked"
    assert len(amended["items"]) == 1

    # 7. The trip is discoverable in the list, filtered by status.
    listed = client.get(
        "/trips", params={"status": "booked", "q": "adventure", "limit": 500}
    ).json()
    assert any(t["id"] == trip_id for t in listed["results"])

    # 8. Cancel the trip (soft) — still retrievable.
    assert client.delete(f"/trips/{trip_id}").json()["status"] == "cancelled"
    assert client.get(f"/trips/{trip_id}").json()["status"] == "cancelled"


def test_trip_reflects_cancelled_booking(client):
    """A booking cancelled after being attached still resolves in the trip view."""
    booking = client.post(
        "/hotels/book",
        json={
            "hotel_id": get_first_hotel_id(client),
            "check_in": VALID_CHECK_IN,
            "check_out": VALID_CHECK_OUT,
            "adults": 1,
            "guest_name": "Refund Me",
            "guest_email": "refund@example.com",
            "guest_phone": "+84 901 234 567",
        },
    ).json()
    trip = client.post(
        "/trips",
        json={
            "name": "Trip with a cancellation",
            "destination_city": "Da Nang",
            "start_date": VALID_CHECK_IN,
            "end_date": VALID_CHECK_OUT,
            "booking_ids": [booking["id"]],
        },
    ).json()

    # Cancel the underlying booking.
    client.post(f"/bookings/{booking['id']}/cancel")

    # The trip still references it; the expanded view shows it as cancelled.
    detail = client.get(f"/trips/{trip['id']}").json()
    assert len(detail["bookings"]) == 1
    assert detail["bookings"][0]["status"] == "cancelled"
