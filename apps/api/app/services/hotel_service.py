"""Hotel lookup + deterministic availability over the DB-backed seed data.

Hotel records are read through ``HotelRepository`` (``app.repositories.hotel_ref``) per
request; ``app/data/hotels.py`` remains the guarded seed source. Availability
is *generated*, never stored — same pattern as ``flight_service``: a query
(hotel + date range) is hashed into an RNG seed, so the same query always
yields the same answer. No availability calendar, no mutable state.
``total_rooms`` is fixed per hotel; ``available_rooms`` varies per date range
(and can be 0 — a fully-booked hotel).

The short-code collision guard now lives in the seeder (``app/db/seed.py``),
which fails fast at seed time; ``HotelRepository.by_short_code`` provides the
``HTL-XXXXXX`` lookup here. The service is bound to the request session via
``get_hotel_service`` (no module-level singleton).
"""

import hashlib
from datetime import datetime
from random import Random
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.text import best_match
from app.db.session import get_session
from app.repositories.hotel_ref import HotelRepository
from app.schemas.hotel import Hotel, HotelAvailability

_DATE_FORMAT = "%Y-%m-%d"


def count_nights(check_in: str, check_out: str) -> int:
    """Number of nights between two YYYY-MM-DD dates.

    Raises ``ValueError`` if either date is not valid ``YYYY-MM-DD``, or if
    ``check_out`` is not strictly after ``check_in``. The latter previously
    clamped to 1 night and silently booked a positive-priced stay — the
    routers wrap this exception into a 422 envelope, so callers now get a
    clear "fix your dates" failure instead of a surprise charge.

    :param check_in: Check-in date (``YYYY-MM-DD``).
    :param check_out: Check-out date (``YYYY-MM-DD``); must be after ``check_in``.
    :return: The number of nights between the two dates.
    """
    nights = (
        datetime.strptime(check_out, _DATE_FORMAT)
        - datetime.strptime(check_in, _DATE_FORMAT)
    ).days
    if nights < 1:
        raise ValueError(f"check_out ({check_out}) must be after check_in ({check_in})")
    return nights


def total_rooms(hotel: Hotel) -> int:
    """Deterministic total room count for a hotel (20–200), fixed per hotel.

    :param hotel: The hotel to size.
    :return: The hotel's total room count (20–200).
    """
    return Random(hotel.id).randint(20, 200)


def max_occupancy(hotel: Hotel) -> int:
    """Max guests one room can hold — larger for higher-star hotels (2–3).

    :param hotel: The hotel whose room capacity to compute.
    :return: The maximum guests per room (2–3).
    """
    return 2 + hotel.star_rating // 3


def available_rooms(hotel: Hotel, check_in: str, check_out: str) -> int:
    """Deterministic rooms free for a date range — 0..``total_rooms``.

    A value of 0 means the hotel is fully booked for those dates. The same
    hotel + dates always returns the same number.

    :param hotel: The hotel to check.
    :param check_in: Check-in date (``YYYY-MM-DD``).
    :param check_out: Check-out date (``YYYY-MM-DD``).
    :return: The number of free rooms (0..``total_rooms``).
    """
    seed = hashlib.md5(f"{hotel.id}-{check_in}-{check_out}".encode()).hexdigest()
    return Random(seed).randint(0, total_rooms(hotel))


def is_available(
    hotel: Hotel, check_in: str, check_out: str, *, rooms: int, guests: int
) -> bool:
    """Whether ``hotel`` can take a booking for the given dates and party.

    True when enough rooms are free *and* the requested rooms can physically
    hold the party (``max_occupancy`` per room).

    :param hotel: The hotel to check.
    :param check_in: Check-in date (``YYYY-MM-DD``).
    :param check_out: Check-out date (``YYYY-MM-DD``).
    :param rooms: Number of rooms requested.
    :param guests: Total number of guests in the party.
    :return: ``True`` if the booking fits, otherwise ``False``.
    """
    free = available_rooms(hotel, check_in, check_out)
    return free >= rooms and max_occupancy(hotel) * rooms >= guests


class HotelService:
    """Hotel lookup + deterministic availability over the DB-backed seed data."""

    def __init__(self, session: Session) -> None:
        self._hotel_repo = HotelRepository(session)

    def list_hotels(self) -> list[Hotel]:
        """Return every seeded hotel.

        :return: All seeded hotels.
        """
        return self._hotel_repo.all()

    def resolve_city(self, name: str | None) -> str | None:
        """Resolve a free-text city name to a canonical hotel city, fuzzily.

        Typo/spacing/case tolerant (e.g. "danang" → "Da Nang"), using the same
        matcher as ``GET /cities?q=``. Returns ``None`` if nothing matches.

        :param name: The free-text city name to resolve (may be ``None``).
        :return: The canonical city name, or ``None`` if nothing matches.
        """
        return best_match(name, self._hotel_repo.distinct_cities(), [lambda c: c])

    def resolve_amenities(self, amenities: list[str] | None) -> list[str] | None:
        """Fuzzy-resolve each requested amenity to its canonical seeded string.

        Typo/plural/substring tolerant (e.g. "wifi" → "Free WiFi"), same matcher
        as :meth:`resolve_city`. An amenity that matches nothing is passed
        through as-is so the repo's containment check still runs — no seed
        amenity will equal it, so it correctly excludes every hotel rather than
        silently guessing.

        :param amenities: Free-text amenity strings, or ``None``.
        :return: Canonicalized amenity strings, or ``None`` if ``amenities`` was falsy.
        """
        if not amenities:
            return None
        catalog = self._hotel_repo.distinct_amenities()
        return [best_match(a, catalog, [lambda c: c]) or a for a in amenities]

    def search_hotels(
        self,
        city: str,
        *,
        min_stars: int | None = None,
        max_price: float | None = None,
        amenities: list[str] | None = None,
    ) -> list[Hotel]:
        """Return hotels in ``city`` with optional filters.

        ``city`` is matched fuzzily (see :meth:`resolve_city`) — a typo or
        partial name still finds the right city. ``amenities`` is a list of
        required amenity strings — all must be present (case-insensitive). An
        unrecognised city returns an empty list (not a 404).

        :param city: The city to search (matched fuzzily).
        :param min_stars: Minimum star rating to include when set.
        :param max_price: Maximum price-per-night to include when set.
        :param amenities: Required amenities; all must be present (case-insensitive).
        :return: The matching hotels, or an empty list if the city is unrecognised.
        """
        resolved = self.resolve_city(city)
        if not resolved:
            return []
        return self._hotel_repo.search(
            city=resolved,
            min_stars=min_stars,
            max_price=max_price,
            amenities=self.resolve_amenities(amenities),
        )

    def get_hotel(self, hotel_id: str) -> Hotel | None:
        """Return the hotel by raw ID *or* its friendly ``HTL-XXXXXX`` short code.

        The short-code lookup is case-insensitive (``htl-ab23xy`` is the same as
        ``HTL-AB23XY``). Returns ``None`` if neither matches.

        :param hotel_id: The raw hotel ID or an ``HTL-XXXXXX`` short code.
        :return: The matching hotel, or ``None`` if neither form matches.
        """
        if not hotel_id:
            return None
        normalised = hotel_id.strip()
        if normalised.upper().startswith("HTL-"):
            return self._hotel_repo.by_short_code(normalised)
        return self._hotel_repo.get(normalised)

    def check_availability(
        self,
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

        :param city: The city to search (matched fuzzily).
        :param check_in: Check-in date (``YYYY-MM-DD``).
        :param check_out: Check-out date (``YYYY-MM-DD``).
        :param rooms: Number of rooms requested.
        :param adults: Number of adults in the party.
        :param children: Number of children in the party.
        :param min_stars: Minimum star rating to include when set.
        :param max_price: Maximum price-per-night to include when set.
        :param amenities: Required amenities; all must be present (case-insensitive).
        :return: ``(nights, results)`` — the night count and per-hotel availability.
        """
        nights = count_nights(check_in, check_out)
        guests = adults + children
        base = self.search_hotels(
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


def get_hotel_service(
    session: Annotated[Session, Depends(get_session)],
) -> HotelService:
    """FastAPI dependency: a hotel service bound to the request session.

    :param session: The request-scoped SQLAlchemy session (injected).
    :return: A ``HotelService`` bound to ``session``.
    """
    return HotelService(session)
