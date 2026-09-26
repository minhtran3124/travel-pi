"""End-to-end search checks for the 20 new gh-237 cities, against a seeded temp
SQLite DB and the real services/repositories: hotel search, flight search (HAN ->
the city's primary airport) and places-by-city lookup must all return results.
Fails until the later waves of specs/gh-237-city-coverage-expansion/PLAN.md add
the actual city/hotel/place data (waves 3-5) -- hotel and place lookups are the
expected red signal until then; flight search is synthetic and route-agnostic, so
it already returns results regardless of city data.
"""

import pytest
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.services.flight_service import FlightService
from app.services.hotel_service import HotelService
from app.services.place_service import PlaceService

from tests.data.test_city_coverage import NEW_CITIES

# The city's primary IATA code per Global Constraints (real airport code, or the
# metropolitan city code when the city has no airport of its own, e.g. Kyoto -> UKY).
PRIMARY_AIRPORT: dict[str, str] = {
    "Osaka": "KIX",
    "Kyoto": "UKY",
    "Fukuoka": "FUK",
    "Sapporo": "CTS",
    "Busan": "PUS",
    "Jeju": "CJU",
    "Taipei": "TPE",
    "Shanghai": "PVG",
    "Beijing": "PEK",
    "Guangzhou": "CAN",
    "Paris": "CDG",
    "London": "LHR",
    "Lisbon": "LIS",
    "Rome": "FCO",
    "Sydney": "SYD",
    "Melbourne": "MEL",
    "Dubai": "DXB",
    "Istanbul": "IST",
    "New York": "JFK",
    "Los Angeles": "LAX",
}

VALID_DEPARTURE_DATE = "2026-06-01"


@pytest.fixture()
def seeded_session(tmp_path):
    db_url = f"sqlite:///{tmp_path}/t.db"
    Base.metadata.create_all(get_engine(db_url), checkfirst=True)
    seed_all(get_session_factory(db_url))
    with get_session_factory(db_url)() as session:
        yield session


@pytest.mark.parametrize("city", NEW_CITIES)
def test_hotel_search_returns_results(seeded_session, city):
    results = HotelService(seeded_session).search_hotels(city)
    assert results, f"{city}: hotel search returned no results"


@pytest.mark.parametrize("city", NEW_CITIES)
def test_flight_search_returns_results(seeded_session, city):
    destination = PRIMARY_AIRPORT[city]
    flights = FlightService(seeded_session).search_flights(
        "HAN", destination, VALID_DEPARTURE_DATE
    )
    assert flights, f"HAN -> {destination} ({city}): flight search returned no results"


@pytest.mark.parametrize("city", NEW_CITIES)
def test_places_by_city_returns_results(seeded_session, city):
    results = PlaceService(seeded_session).search_places(city=city)
    assert len(results) >= 8, (
        f"{city}: places search returned {len(results)}, expected >=8"
    )
