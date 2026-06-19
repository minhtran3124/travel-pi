"""Hotel lookup + deterministic availability over the DB-backed seed data.

Hotel records are read through ``hotel_repo`` (``app.crud.hotel_ref``) per
request; ``app/data/hotels.py`` remains the guarded seed source. Availability
is *generated*, never stored — same pattern as ``flight_service``: a query
(hotel + date range) is hashed into an RNG seed, so the same query always
yields the same answer. No availability calendar, no mutable state.
``total_rooms`` is fixed per hotel; ``available_rooms`` varies per date range
(and can be 0 — a fully-booked hotel).

The short-code collision guard now lives in the seeder (``app/db/seed.py``),
which fails fast at seed time; ``hotel_repo.by_short_code`` provides the
``HTL-XXXXXX`` lookup here.
"""

import hashlib
from datetime import datetime
from random import Random

from app.core.config import get_settings
from app.core.text import best_match
from app.crud.hotel_ref import HotelRepository
from app.db.engine import get_session_factory
from app.schemas.hotel import Hotel, HotelAvailability

# Hotels are DB-backed. The repo is built from the configured DB at import time;
# it is NOT a FastAPI dependency, so tests repoint it via ``set_hotel_repo``
# after seeding the temp DB (see tests/conftest.py).
_hotel_repo = HotelRepository(get_session_factory(get_settings().database_url))


def set_hotel_repo(repo: HotelRepository) -> None:
    """Point hotel reads at a different store — used by tests to read the seeded
    temporary database instead of the real travel.db."""
    global _hotel_repo
    _hotel_repo = repo


_DATE_FORMAT = "%Y-%m-%d"


def list_hotels() -> list[Hotel]:
    """Return every seeded hotel."""
    return _hotel_repo.all()


def count_nights(check_in: str, check_out: str) -> int:
    """Number of nights between two YYYY-MM-DD dates.

    Raises ``ValueError`` if either date is not valid ``YYYY-MM-DD``, or if
    ``check_out`` is not strictly after ``check_in``. The latter previously
    clamped to 1 night and silently booked a positive-priced stay — the
    routers wrap this exception into a 422 envelope, so callers now get a
    clear "fix your dates" failure instead of a surprise charge.
    """
    nights = (
        datetime.strptime(check_out, _DATE_FORMAT)
        - datetime.strptime(check_in, _DATE_FORMAT)
    ).days
    if nights < 1:
        raise ValueError(f"check_out ({check_out}) must be after check_in ({check_in})")
    return nights


def total_rooms(hotel: Hotel) -> int:
    """Deterministic total room count for a hotel (20–200), fixed per hotel."""
    return Random(hotel.id).randint(20, 200)


def max_occupancy(hotel: Hotel) -> int:
    """Max guests one room can hold — larger for higher-star hotels (2–3)."""
    return 2 + hotel.star_rating // 3


def available_rooms(hotel: Hotel, check_in: str, check_out: str) -> int:
    """Deterministic rooms free for a date range — 0..``total_rooms``.

    A value of 0 means the hotel is fully booked for those dates. The same
    hotel + dates always returns the same number.
    """
    seed = hashlib.md5(f"{hotel.id}-{check_in}-{check_out}".encode()).hexdigest()
    return Random(seed).randint(0, total_rooms(hotel))


def resolve_city(name: str | None) -> str | None:
    """Resolve a free-text city name to a canonical hotel city, fuzzily.

    Typo/spacing/case tolerant (e.g. "danang" → "Da Nang"), using the same
    matcher as ``GET /cities?q=``. Returns ``None`` if nothing matches.
    """
    return best_match(name, _hotel_repo.distinct_cities(), [lambda c: c])


def search_hotels(
    city: str,
    *,
    min_stars: int | None = None,
    max_price: float | None = None,
    amenities: list[str] | None = None,
) -> list[Hotel]:
    """Return hotels in ``city`` with optional filters.

    ``city`` is matched fuzzily (see :func:`resolve_city`) — a typo or
    partial name still finds the right city. ``amenities`` is a list of
    required amenity strings — all must be present (case-insensitive). An
    unrecognised city returns an empty list (not a 404).
    """
    resolved = resolve_city(city)
    if not resolved:
        return []
    return _hotel_repo.search(
        city=resolved,
        min_stars=min_stars,
        max_price=max_price,
        amenities=amenities,
    )


def get_hotel(hotel_id: str) -> Hotel | None:
    """Return the hotel by raw ID *or* its friendly ``HTL-XXXXXX`` short code.

    The short-code lookup is case-insensitive (``htl-ab23xy`` is the same as
    ``HTL-AB23XY``). Returns ``None`` if neither matches.
    """
    if not hotel_id:
        return None
    normalised = hotel_id.strip()
    if normalised.upper().startswith("HTL-"):
        return _hotel_repo.by_short_code(normalised)
    return _hotel_repo.get(normalised)


def is_available(
    hotel: Hotel, check_in: str, check_out: str, *, rooms: int, guests: int
) -> bool:
    """Whether ``hotel`` can take a booking for the given dates and party.

    True when enough rooms are free *and* the requested rooms can physically
    hold the party (``max_occupancy`` per room).
    """
    free = available_rooms(hotel, check_in, check_out)
    return free >= rooms and max_occupancy(hotel) * rooms >= guests


def check_availability(
    city: str,
    check_in: str,
    check_out: str,
    *,
    rooms: int = 1,
    adults: int = 2,
    children: int = 0,
    min_stars: int | None = None,
    max_price: float | None = None,
    amenities: list[str] | None = None,
) -> tuple[int, list[HotelAvailability]]:
    """Return ``(nights, results)`` — hotels matching ``city``/filters, each
    annotated with availability.

    Each result carries ``available`` (can it take this booking), the free
    room count, per-room capacity, and the all-in ``total_price``
    (``price_per_night × nights × rooms``). ``nights`` is returned alongside
    so the caller can echo it even when no hotels match (empty ``results``).
    Raises ``ValueError`` if the dates are not valid ``YYYY-MM-DD``.
    """
    nights = count_nights(check_in, check_out)
    guests = adults + children
    base = search_hotels(
        city, min_stars=min_stars, max_price=max_price, amenities=amenities
    )
    results: list[HotelAvailability] = []
    for hotel in base:
        free = available_rooms(hotel, check_in, check_out)
        occupancy = max_occupancy(hotel)
        results.append(
            HotelAvailability(
                **hotel.model_dump(),
                available=free >= rooms and occupancy * rooms >= guests,
                available_rooms=free,
                max_occupancy_per_room=occupancy,
                nights=nights,
                total_price=round(hotel.price_per_night * nights * rooms, 2),
            )
        )
    return nights, results
