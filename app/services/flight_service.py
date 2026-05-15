"""Deterministic flight generation, search, and lookup.

Flights are never persisted. They are generated on demand from the search
parameters using a seed derived from ``origin + destination + date``, so the
same query always returns the same flights. This lets the agent reference
"the 7:15 Bamboo flight" across turns, and lets the FE re-fetch a flight by
its ID.

``search_flights`` adds an optional filter + sort layer on top of the
deterministic generation: the 5 flights for a route+date never change, but a
caller can narrow them by airline / price / stops and reorder them.
"""

import hashlib
import random
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

from app.core.config import get_settings
from app.crud.flight import FlightIndexRepository
from app.data.airlines import AIRLINES
from app.schemas.flight import Airline, Flight

# Fixed namespace for deterministic flight UUIDs (UUID5).
_FLIGHT_NS = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

# Flight IDs are a one-way uuid5 hash of their search params, so a lookup
# can't decode the ID — it needs the params on file. They are persisted in
# SQLite (so a flight ID resolves across restarts and worker processes), with
# this in-process dict as a write-through cache to skip the DB on a repeat
# search of a route already seen this process.
_flight_index: dict[str, tuple[str, str, str]] = {}
_index_repo = FlightIndexRepository(get_settings().database_path)


def init_flight_index() -> None:
    """Create the flight-index table. Called once on application startup."""
    _index_repo.init_db()


def set_index_repo(repo: FlightIndexRepository) -> None:
    """Point flight-ID lookups at a different store — used by tests to isolate
    persistence into a temporary database."""
    global _index_repo
    _index_repo = repo
    _flight_index.clear()

FLIGHTS_PER_SEARCH = 5
_DEPARTURE_MINUTES = (0, 15, 30, 45)
_STOPS_DISTRIBUTION = (0, 0, 0, 1)  # 75% direct, 25% one stop

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
    """Derive a stable 32-bit RNG seed from the search parameters.

    We hash with MD5 (not Python's built-in ``hash()``) because ``hash()`` is
    randomised per process — it would give different flights every time the
    server restarts. MD5 of the same string is identical forever, which is
    exactly the determinism we need. ``% (2**32)`` trims the 128-bit digest
    down to the 32-bit integer ``random.Random`` expects as a seed.
    """
    seed_str = f"{origin}-{destination}-{departure_date}"
    digest = hashlib.md5(seed_str.encode()).hexdigest()
    return int(digest, 16) % (2**32)


def generate_flights(
    origin: str,
    destination: str,
    departure_date: str,
    count: int = FLIGHTS_PER_SEARCH,
) -> list[Flight]:
    """Generate ``count`` deterministic flights, sorted by departure time.

    Important: the *order* of the ``rng.*`` calls below is part of the
    contract. Re-ordering, adding, or removing any ``rng`` call shifts the
    whole pseudo-random sequence, so every previously issued flight ID would
    resolve to different data. Change with care.

    Raises ``ValueError`` if ``departure_date`` is not a valid YYYY-MM-DD date.
    """
    rng = random.Random(_seed_for(origin, destination, departure_date))
    base_date = datetime.strptime(departure_date, "%Y-%m-%d")

    flights: list[Flight] = []
    new_rows: list[tuple[str, str, str, str]] = []
    for index in range(count):
        airline = rng.choice(AIRLINES)
        departure = base_date.replace(
            hour=rng.randint(5, 22),
            minute=rng.choice(_DEPARTURE_MINUTES),
        )
        duration_minutes = rng.randint(80, 360)  # 1h20m to 6h
        slug = f"FL_{origin}{destination}_{base_date:%Y%m%d}_{index:02d}"
        flight_id = str(uuid.uuid5(_FLIGHT_NS, slug))
        if flight_id not in _flight_index:
            _flight_index[flight_id] = (origin, destination, departure_date)
            new_rows.append((flight_id, origin, destination, departure_date))
        flights.append(
            Flight(
                id=flight_id,
                airline=Airline(**airline),
                flight_number=f"{airline['code']}{rng.randint(100, 999)}",
                origin=origin,
                destination=destination,
                departure_time=departure,
                arrival_time=departure + timedelta(minutes=duration_minutes),
                duration_minutes=duration_minutes,
                price=round(rng.uniform(50, 800), 2),
                seats_available=rng.randint(1, 50),
                stops=rng.choice(_STOPS_DISTRIBUTION),
            )
        )

    # Persist any newly seen flight IDs so they resolve after a restart.
    _index_repo.remember_many(new_rows)

    flights.sort(key=lambda flight: flight.departure_time)
    return flights


def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    *,
    airline: str | None = None,
    max_price: float | None = None,
    max_stops: int | None = None,
    sort: str = DEFAULT_SORT,
) -> list[Flight]:
    """Generate a route's flights, then apply optional filters and sorting.

    Generation stays deterministic — the same route + date always yields the
    same 5 flights. The filters only narrow that set (so the result has 0-5
    flights) and ``sort`` reorders it. An unknown ``sort`` value falls back to
    the default.

    Raises ``ValueError`` if ``departure_date`` is not a valid YYYY-MM-DD date.
    """
    flights = generate_flights(origin, destination, departure_date)

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
    flight_number: str,
    origin: str,
    destination: str,
    departure_date: str,
) -> Flight | None:
    """Resolve a human-friendly flight reference (e.g. ``"VN123"``) to a Flight.

    Booking by UUID was hostile to agents — they don't see UUIDs in search
    results. ``flight_number`` alone isn't unique either (the same code is
    reused across dates and routes), so the route+date qualifier is required:
    together they pin a single flight from the 5 our generator returns.

    Match is case-insensitive (``"vn123"`` resolves the same as ``"VN123"``);
    spaces are stripped (``"VN 123"`` works too). Returns ``None`` if no
    flight in the route+date set carries that number, or if the date doesn't
    parse.
    """
    try:
        candidates = generate_flights(origin, destination, departure_date)
    except ValueError:
        return None
    needle = flight_number.replace(" ", "").upper()
    for flight in candidates:
        if flight.flight_number.upper() == needle:
            return flight
    return None


def find_flight_by_id(flight_id: str) -> Flight | None:
    """Resolve a flight UUID back to its flight.

    A flight ID maps to the search params that generated it — first via the
    in-process cache, then the persisted ``flight_index`` table. We re-run the
    generator for those params (deterministic — identical result every time)
    and return the matching flight. Returns ``None`` if the UUID was never
    issued by this deployment or is invalid.
    """
    params = _flight_index.get(flight_id)
    if params is None:
        params = _index_repo.lookup(flight_id)
        if params is None:
            return None
        _flight_index[flight_id] = params
    origin, destination, departure_date = params
    for flight in generate_flights(origin, destination, departure_date):
        if flight.id == flight_id:
            return flight
    return None


def list_airlines() -> list[Airline]:
    """Return the airlines available as a flight-search filter option."""
    return [Airline(**airline) for airline in AIRLINES]


def sort_options() -> list[tuple[str, str]]:
    """Return ``(value, label)`` pairs for the flight-search sort dropdown."""
    return [(value, spec[0]) for value, spec in FLIGHT_SORTS.items()]
