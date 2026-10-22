"""Deterministic flight generation, search, and lookup — flights are generated on demand from the query (never persisted), so the same query always returns the same flights."""

import hashlib
import random
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.geo import haversine_km
from app.db.engine import get_session_factory
from app.db.session import get_session
from app.repositories.airline import AirlineRepository
from app.repositories.airport import AirportRepository
from app.repositories.city import CityRepository
from app.repositories.flight import FlightIndexRepository
from app.schemas.flight import Airline, Flight

# Fixed namespace for deterministic flight UUIDs (UUID5).
_FLIGHT_NS = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

# Process-wide write-through cache (flight_id -> search params) over the persisted flight_index; module-level so it is shared across requests.
_flight_index: dict[str, tuple[str, str, str]] = {}

FLIGHTS_PER_SEARCH = 5
_DEPARTURE_MINUTES = (0, 15, 30, 45)
_STOPS_DISTRIBUTION = (0, 0, 0, 1)  # 75% direct, 25% one stop

# Long-haul overrides: beyond this great-circle distance the short-haul rng
# draws (80-360 min, $50-800) understate reality (e.g. HAN->JFK), so duration
# and price are recomputed from the distance instead, using the already-drawn
# values only as a deterministic jitter/scale input (no extra rng calls).
_LONG_HAUL_KM = 4500.0
_LONG_HAUL_CRUISE_KMH = 820.0  # typical widebody cruise speed
_LONG_HAUL_BASE_MINUTES = 40  # taxi/climb/descent overhead
_LONG_HAUL_JITTER_MINUTES = 60  # spread across the drawn duration's range
_LONG_HAUL_STOP_MINUTES = 150  # extra layover for a 1-stop long-haul (~2.5h)
_LONG_HAUL_PRICE_MIN_PER_KM = 0.09
_LONG_HAUL_PRICE_MAX_PER_KM = 0.14
# Each stop on a long-haul route adds a layover-city surcharge rather than a discount:
# unlike a short domestic hop, a 1-stop long-haul usually connects through a pricier hub
# and adds fare-basis complexity, so it is modelled as strictly more expensive.
_LONG_HAUL_STOP_SURCHARGE_PER_STOP = 0.08

# Sort key -> (UI label, sort function, reverse flag) for flight search.
FLIGHT_SORTS: dict[str, tuple[str, Callable[[Flight], object], bool]] = {
    "departure_asc": ("Departure — earliest first", lambda f: f.departure_time, False),
    "departure_desc": ("Departure — latest first", lambda f: f.departure_time, True),
    "price_asc": ("Price — lowest first", lambda f: f.price, False),
    "price_desc": ("Price — highest first", lambda f: f.price, True),
    "duration_asc": ("Duration — shortest first", lambda f: f.duration_minutes, False),
    "duration_desc": ("Duration — longest first", lambda f: f.duration_minutes, True),
}
DEFAULT_SORT = "departure_asc"


def _seed_for(origin: str, destination: str, departure_date: str) -> int:
    """Stable 32-bit RNG seed from the search params; MD5 (not ``hash()``, which is per-process randomised) so it survives restarts."""
    seed_str = f"{origin}-{destination}-{departure_date}"
    digest = hashlib.md5(seed_str.encode()).hexdigest()
    return int(digest, 16) % (2**32)


def _long_haul_duration_price(
    distance_km: float,
    drawn_duration_minutes: int,
    drawn_price: float,
    stops: int,
) -> tuple[int, float]:
    """Recompute duration/price for a long-haul route from distance + the already-drawn short-haul values (no new rng draws, so flight IDs stay untouched).

    Price is anchored at the drawn short-haul value at the ``_LONG_HAUL_KM`` boundary
    (``distance_km - _LONG_HAUL_KM`` starts at ~0 just past the cutoff) and grows with the
    extra distance beyond it, so the long-haul band never dips below the short-haul band's
    top ($800) right at the boundary the way a flat per-km rate did.
    """
    duration_minutes = round(
        distance_km / _LONG_HAUL_CRUISE_KMH * 60
        + _LONG_HAUL_BASE_MINUTES
        + (drawn_duration_minutes - 80) / 280 * _LONG_HAUL_JITTER_MINUTES
    )
    if stops:
        duration_minutes += _LONG_HAUL_STOP_MINUTES

    price_fraction = (drawn_price - 50) / (800 - 50)
    per_km = _LONG_HAUL_PRICE_MIN_PER_KM + price_fraction * (
        _LONG_HAUL_PRICE_MAX_PER_KM - _LONG_HAUL_PRICE_MIN_PER_KM
    )
    price = drawn_price + (distance_km - _LONG_HAUL_KM) * per_km
    price *= 1 + _LONG_HAUL_STOP_SURCHARGE_PER_STOP * stops
    return duration_minutes, round(price, 2)


class FlightService:
    """Deterministic flight generation, search, and lookup."""

    def __init__(self, session: Session) -> None:
        # Airline list order (ORDER BY position) is load-bearing for flight determinism.
        self._airline = AirlineRepository(session)
        self._index = FlightIndexRepository(session)
        self._airport = AirportRepository(session)
        self._city = CityRepository(session)

    def _coords_for(self, airport_code: str) -> tuple[float, float] | None:
        """Resolve an IATA code to its city's seeded (lat, lon); ``None`` if the airport or its city coords are unknown."""
        airport = self._airport.get(airport_code)
        if airport is None:
            return None
        city = self._city.get(airport.city)
        if city is None or city.latitude is None or city.longitude is None:
            return None
        return city.latitude, city.longitude

    def generate_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        count: int = FLIGHTS_PER_SEARCH,
    ) -> list[Flight]:
        """Generate ``count`` deterministic flights, sorted by departure time. The order of the ``rng.*`` calls below is contractual — changing it reissues every flight ID."""
        rng = random.Random(_seed_for(origin, destination, departure_date))
        base_date = datetime.strptime(departure_date, "%Y-%m-%d")

        # Must stay in seed (position) order so rng.choice is stable — do not reorder.
        airlines = self._airline.list()

        origin_coords = self._coords_for(origin)
        destination_coords = self._coords_for(destination)
        distance_km = (
            haversine_km(*origin_coords, *destination_coords)
            if origin_coords is not None and destination_coords is not None
            else None
        )
        is_long_haul = distance_km is not None and distance_km > _LONG_HAUL_KM

        flights: list[Flight] = []
        new_rows: list[tuple[str, str, str, str]] = []
        for index in range(count):
            # Draw order below is contractual (see class docstring) — every rng
            # call stays in place even for a long-haul route; only the derived
            # duration/price are replaced afterwards.
            airline = rng.choice(airlines)
            departure = base_date.replace(
                hour=rng.randint(5, 22),
                minute=rng.choice(_DEPARTURE_MINUTES),
            )
            duration_minutes = rng.randint(80, 360)  # 1h20m to 6h
            flight_number = f"{airline['code']}{rng.randint(100, 999)}"
            price = round(rng.uniform(50, 800), 2)
            seats_available = rng.randint(1, 50)
            stops = rng.choice(_STOPS_DISTRIBUTION)

            if is_long_haul:
                duration_minutes, price = _long_haul_duration_price(
                    distance_km, duration_minutes, price, stops
                )

            slug = f"FL_{origin}{destination}_{base_date:%Y%m%d}_{index:02d}"
            flight_id = str(uuid.uuid5(_FLIGHT_NS, slug))
            if flight_id not in _flight_index:
                _flight_index[flight_id] = (origin, destination, departure_date)
                new_rows.append((flight_id, origin, destination, departure_date))
            flights.append(
                Flight(
                    id=flight_id,
                    airline=Airline(**airline),
                    flight_number=flight_number,
                    origin=origin,
                    destination=destination,
                    departure_time=departure,
                    arrival_time=departure + timedelta(minutes=duration_minutes),
                    duration_minutes=duration_minutes,
                    price=price,
                    seats_available=seats_available,
                    stops=stops,
                )
            )

        # Persist any newly seen flight IDs so they resolve after a restart.
        self._index.remember_many(new_rows)

        flights.sort(key=lambda flight: flight.departure_time)
        return flights

    def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        *,
        airline: str | None = None,
        max_price: float | None = None,
        max_stops: int | None = None,
        sort: str = DEFAULT_SORT,
    ) -> list[Flight]:
        """Generate a route's flights, then apply optional filters and sorting; an unknown ``sort`` falls back to the default."""
        flights = self.generate_flights(origin, destination, departure_date)

        if airline:
            code = airline.upper()
            flights = [flight for flight in flights if flight.airline.code == code]
        if max_price is not None:
            flights = [flight for flight in flights if flight.price <= max_price]
        if max_stops is not None:
            flights = [flight for flight in flights if flight.stops <= max_stops]

        _label, key, reverse = FLIGHT_SORTS.get(sort, FLIGHT_SORTS[DEFAULT_SORT])
        return sorted(flights, key=key, reverse=reverse)

    def find_flight_by_number(
        self,
        flight_number: str,
        origin: str,
        destination: str,
        departure_date: str,
    ) -> Flight | None:
        """Resolve a human-friendly flight reference (e.g. ``"VN123"``) to a Flight; the route+date qualifier is required since a flight number repeats across routes/dates. Case-insensitive, spaces stripped; ``None`` if nothing matches or the date is invalid."""
        try:
            candidates = self.generate_flights(origin, destination, departure_date)
        except ValueError:
            return None
        needle = flight_number.replace(" ", "").upper()
        for flight in candidates:
            if flight.flight_number.upper() == needle:
                return flight
        return None

    def find_flight_by_id(self, flight_id: str) -> Flight | None:
        """Resolve a flight UUID back to its flight by re-running the generator for its stored search params; ``None`` if the UUID is unknown or invalid."""
        params = _flight_index.get(flight_id)
        if params is None:
            params = self._index.lookup(flight_id)
            if params is None:
                return None
            _flight_index[flight_id] = params
        origin, destination, departure_date = params
        for flight in self.generate_flights(origin, destination, departure_date):
            if flight.id == flight_id:
                return flight
        return None

    def list_airlines(self) -> list[Airline]:
        """Return the airlines available as a flight-search filter option, in seed order."""
        return [Airline(**airline) for airline in self._airline.list()]

    def sort_options(self) -> list[tuple[str, str]]:
        """Return ``(value, label)`` pairs for the flight-search sort dropdown."""
        return [(value, spec[0]) for value, spec in FLIGHT_SORTS.items()]


def init_flight_index() -> None:
    """Create the flight-index table (startup; no request context, uses the factory)."""
    FlightIndexRepository(get_session_factory(get_settings().database_url)).init_db()


def get_flight_service(
    session: Annotated[Session, Depends(get_session)],
) -> FlightService:
    """FastAPI dependency: a flight service bound to the request session."""
    return FlightService(session)
