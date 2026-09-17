"""The `passengers` field defaults to one seat at the single fare."""

from tests.conftest import (
    VALID_DATE,
    VALID_DESTINATION,
    VALID_ORIGIN,
    get_first_flight_booking_fields,
)


def _first_flight_fare(client) -> float:
    results = client.get(
        "/flights/search",
        params={
            "origin": VALID_ORIGIN,
            "destination": VALID_DESTINATION,
            "departure_date": VALID_DATE,
        },
    ).json()["results"]
    return results[0]["price"]


def _book(client, **overrides):
    return client.post(
        "/flights/book",
        json={
            **get_first_flight_booking_fields(client),
            "passenger_name": "Test User",
            "passenger_email": "test@example.com",
            "passenger_phone": "+84 901 234 567",
            **overrides,
        },
    )


def test_books_n_seats_at_n_times_the_fare(client):
    fare = _first_flight_fare(client)

    resp = _book(client, passengers=3)

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_price"] == fare * 3
    assert body["details"]["passengers"] == 3


def test_defaults_to_one_seat_at_the_single_fare(client):
    fare = _first_flight_fare(client)

    resp = _book(client)

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_price"] == fare
    assert body["details"]["passengers"] == 1


def test_invalid_passenger_count_is_422(client):
    resp = _book(client, passengers=0)

    assert resp.status_code == 422
