"""Seed-data invariants checked once at startup.

The CLAUDE.md contract promises "every city has ≥3 hotels and ≥3 places".
Without an enforced check, a typo in a hotel's ``city`` or a forgotten place
entry quietly violates that promise — and the regression only surfaces when
a user happens to search the affected city. This module fails loud at boot
instead.

The check runs AFTER the seeder populates the DB (see ``core/lifespan.py``), so
it reads the seeded reference tables through the repos rather than the
``app/data`` caches.
"""

from app.core.config import get_settings
from app.crud.city import CityRepository
from app.crud.hotel_ref import HotelRepository
from app.crud.place_ref import PlaceRepository
from app.db.engine import get_session_factory

_MIN_PER_CITY = 3


def check_city_coverage() -> None:
    """Assert every seeded city has at least the minimum hotels and places.

    Reads the seeded ``cities``/``hotels``/``places`` tables via the repos.
    Raises :class:`RuntimeError` listing the offending cities — fail loud at
    startup rather than ship data that breaks the contract.
    """
    session_factory = get_session_factory(get_settings().database_url)
    city_repo = CityRepository(session_factory)
    hotel_repo = HotelRepository(session_factory)
    place_repo = PlaceRepository(session_factory)

    city_names = {city.name for city in city_repo.list_with_counts()}
    hotel_counts = hotel_repo.count_by_city()
    place_counts = place_repo.count_by_city()

    short_hotels = sorted(
        name for name in city_names if hotel_counts.get(name, 0) < _MIN_PER_CITY
    )
    short_places = sorted(
        name for name in city_names if place_counts.get(name, 0) < _MIN_PER_CITY
    )

    problems: list[str] = []
    if short_hotels:
        problems.append(
            f"cities with < {_MIN_PER_CITY} hotels: "
            + ", ".join(
                f"{name} ({hotel_counts.get(name, 0)})" for name in short_hotels
            )
        )
    if short_places:
        problems.append(
            f"cities with < {_MIN_PER_CITY} places: "
            + ", ".join(
                f"{name} ({place_counts.get(name, 0)})" for name in short_places
            )
        )

    if problems:
        raise RuntimeError("Seed-data invariant violated — " + "; ".join(problems))
