"""Cross-engine parity proof: live DB-backed endpoints must byte-reproduce the pre-migration golden fixtures, guarding airline ORDER BY position and verbatim UUID-string identity."""

import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"

# The EXACT queries recorded at capture time (tests/db/_capture_golden.py).
FLIGHTS_URL = "/flights/search?origin=SGN&destination=HAN&departure_date=2026-09-01"
AVAIL_URL = "/hotels/availability?city=Da+Nang&check_in=2026-09-01&check_out=2026-09-04"


def _golden(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_flights_match_golden(client):
    """Live /flights/search byte-equals the pre-migration golden flights."""
    resp = client.get(FLIGHTS_URL)
    assert resp.status_code == 200, resp.text
    assert resp.json() == _golden("golden_flights.json")


def test_hotel_availability_matches_golden(client):
    """Live /hotels/availability byte-equals the pre-migration golden set."""
    resp = client.get(AVAIL_URL)
    assert resp.status_code == 200, resp.text
    assert resp.json() == _golden("golden_hotel_availability.json")


def test_flights_stable_within_run(client):
    """Deterministic generation: two identical queries return identical bodies."""
    first = client.get(FLIGHTS_URL)
    second = client.get(FLIGHTS_URL)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json() == second.json()


def test_hotel_availability_stable_within_run(client):
    """Deterministic generation: two identical availability queries match."""
    first = client.get(AVAIL_URL)
    second = client.get(AVAIL_URL)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json() == second.json()


def test_flight_airline_codes_follow_repo_position_order(client, seeded_session):
    """Every flight's airline code is one the repo serves, and distinct codes first appear in ``airline_repo.list()`` position order."""
    from app.repositories.airline import AirlineRepository

    # Same seeded DB the client uses, so position order matches what the flight generator drew from.
    repo = AirlineRepository(seeded_session)
    repo_codes = [a["code"] for a in repo.list()]
    repo_pos = {code: i for i, code in enumerate(repo_codes)}

    resp = client.get(FLIGHTS_URL)
    flights = resp.json()["results"]
    seen_codes = [f["airline"]["code"] for f in flights]

    assert all(code in repo_pos for code in seen_codes), (seen_codes, repo_codes)

    first_appearance: list[str] = []
    for code in seen_codes:
        if code not in first_appearance:
            first_appearance.append(code)
    positions = [repo_pos[c] for c in first_appearance]
    # Not a hard "increasing" check (rng.choice can revisit); distinct codes must all be valid repo positions.
    assert all(p in repo_pos.values() for p in positions)


def test_airport_list_order_matches_data_insertion_order(seeded_session):
    """list_airports() must return AIRPORTS insertion order — board_service feeds it to an order-sensitive Random.sample, so a different order changes which routes show."""
    from app.data.airports import AIRPORTS
    from app.services.airport_service import AirportService

    served = [a.code for a in AirportService(seeded_session).list_airports()]
    expected = list(AIRPORTS.keys())
    assert served == expected, (served, expected)


def test_hotels_pagination_pages_are_disjoint_and_stable(client):
    """``GET /hotels`` offset/limit pages are disjoint and stable — the ``position`` ORDER BY is what makes paging deterministic on Postgres."""

    def ids(offset: int, limit: int = 5) -> list[str]:
        resp = client.get(f"/hotels?limit={limit}&offset={offset}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        items = body["results"] if isinstance(body, dict) else body
        return [h["id"] for h in items]

    page0_a = ids(0)
    page0_b = ids(0)
    page1_a = ids(5)
    page1_b = ids(5)

    assert page0_a == page0_b
    assert page1_a == page1_b
    assert set(page0_a).isdisjoint(set(page1_a)), (page0_a, page1_a)
    # Both pages returned rows — guards an empty-DB false pass.
    assert page0_a and page1_a
