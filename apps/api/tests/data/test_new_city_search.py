"""End-to-end search checks for the 20 new gh-237 cities, against a seeded temp
SQLite DB and the real services/repositories: hotel search (date/availability
based), flight search (HAN -> the city's primary airport, once that airport is
confirmed seeded and registered to the city) and places-by-city lookup must all
return results. Fails until the later waves of specs/gh-237-city-coverage-expansion/
PLAN.md add the actual city/hotel/place data (waves 3-5) -- hotel and place
lookups are the expected red signal until then.
"""

import pytest
from app.data.airports import AIRPORTS
from app.data.cities import CITIES
from app.db.base import Base
from app.db.engine import get_engine, get_session_factory
from app.db.seed import seed_all
from app.repositories.airport import AirportRepository
from app.services.flight_service import FlightService
from app.services.hotel_service import HotelService
from app.services.place_service import PlaceService

from tests.data.test_city_coverage import NEW_CITIES

# The city's primary IATA code per Global Constraints (real airport code, or the
# metropolitan city code when the city has no airport of its own, e.g. Kyoto ->
# UKY for hotel-code purposes only). Kyoto has no UKY *airport* in foundations --
# UKY is an IATA metropolitan city code, not an airport code -- so its primary
# airport for search purposes is Kansai (KIX), shared with Osaka.
PRIMARY_AIRPORT: dict[str, str] = {
    "Osaka": "KIX",
    "Kyoto": "KIX",
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

VALID_CHECK_IN = "2026-06-01"
VALID_CHECK_OUT = "2026-06-05"
VALID_DEPARTURE_DATE = "2026-06-01"


def _city_record(name: str) -> dict | None:
    return next((c for c in CITIES if c["name"] == name), None)


@pytest.fixture(scope="module")
def seeded_session_factory(tmp_path_factory):
    """A seeded temp-SQLite session factory shared by this module's tests."""
    db_file = tmp_path_factory.mktemp("new_city_search") / "t.db"
    db_url = f"sqlite:///{db_file}"
    Base.metadata.create_all(get_engine(db_url), checkfirst=True)
    seed_all(get_session_factory(db_url))
    return get_session_factory(db_url)


@pytest.fixture()
def seeded_session(seeded_session_factory):
    with seeded_session_factory() as session:
        yield session


@pytest.mark.parametrize("city", NEW_CITIES)
def test_hotel_search_returns_available_results_for_date_range(seeded_session, city):
    service = HotelService(seeded_session)
    resolved = service.resolve_city(city)
    assert resolved == city, f"{city}: hotel city resolves to {resolved!r}"
    _nights, results = service.check_availability(city, VALID_CHECK_IN, VALID_CHECK_OUT)
    available = [r for r in results if r.available]
    assert available, (
        f"{city}: check_availability({VALID_CHECK_IN}..{VALID_CHECK_OUT}) "
        f"returned no available hotels (got {len(results)} total)"
    )


@pytest.mark.parametrize("city", NEW_CITIES)
def test_flight_search_returns_results(seeded_session_factory, city):
    destination = PRIMARY_AIRPORT[city]

    record = _city_record(city)
    assert record is not None, f"{city}: missing from app.data.cities.CITIES"
    assert destination in record["airport_codes"] and destination in AIRPORTS, (
        f"{city}: primary airport {destination!r} must be in both "
        f"CITIES[{city!r}]['airport_codes'] and app.data.airports.AIRPORTS"
    )

    with seeded_session_factory() as session:
        seeded = AirportRepository(session).get(destination)
    assert seeded is not None, (
        f"{city}: primary airport {destination!r} is not seeded in the airports table"
    )
    assert seeded.city == city or destination in record["airport_codes"], (
        f"{city}: seeded airport {destination!r} belongs to {seeded.city!r}, "
        f"not {city!r} nor listed in its airport_codes"
    )

    with seeded_session_factory() as session:
        flights = FlightService(session).search_flights(
            "HAN", destination, VALID_DEPARTURE_DATE
        )
    assert flights, f"HAN -> {destination} ({city}): flight search returned no flights"


@pytest.mark.parametrize("city", NEW_CITIES)
def test_places_by_city_returns_results(seeded_session, city):
    service = PlaceService(seeded_session)
    resolved = service.resolve_city(city)
    assert resolved == city, f"{city}: place city resolves to {resolved!r}"
    results = service.search_places(city=city)
    assert len(results) >= 8, (
        f"{city}: places search returned {len(results)}, expected >=8"
    )
