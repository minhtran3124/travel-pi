"""Startup check enforcing the CLAUDE.md contract that every city has ≥3 hotels and ≥3 places — fails loud at boot rather than at a user's first search."""

from app.core.config import get_settings
from app.db.engine import get_session_factory
from app.repositories.city import CityRepository
from app.repositories.hotel_ref import HotelRepository
from app.repositories.place_ref import PlaceRepository

_MIN_PER_CITY = 3


def check_city_coverage() -> None:
    """Assert every seeded city has at least the minimum hotels and places, raising :class:`RuntimeError` listing offenders."""
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
