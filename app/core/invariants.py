"""Seed-data invariants checked once at startup.

The CLAUDE.md contract promises "every city has ≥3 hotels and ≥3 places".
Without an enforced check, a typo in a hotel's ``city`` or a forgotten place
entry quietly violates that promise — and the regression only surfaces when
a user happens to search the affected city. This module fails loud at boot
instead.
"""

from collections import Counter

from app.data.cities import CITIES
from app.data.hotels import HOTELS
from app.data.places import PLACES

_MIN_PER_CITY = 3


def check_city_coverage() -> None:
    """Assert every seeded city has at least the minimum hotels and places.

    Raises :class:`RuntimeError` listing the offending cities — fail loud at
    startup rather than ship data that breaks the contract.
    """
    city_names = {city["name"] for city in CITIES}
    hotel_counts = Counter(hotel["city"] for hotel in HOTELS)
    place_counts = Counter(place["city"] for place in PLACES)

    short_hotels = sorted(
        name for name in city_names if hotel_counts[name] < _MIN_PER_CITY
    )
    short_places = sorted(
        name for name in city_names if place_counts[name] < _MIN_PER_CITY
    )

    problems: list[str] = []
    if short_hotels:
        problems.append(
            f"cities with < {_MIN_PER_CITY} hotels: "
            + ", ".join(f"{name} ({hotel_counts[name]})" for name in short_hotels)
        )
    if short_places:
        problems.append(
            f"cities with < {_MIN_PER_CITY} places: "
            + ", ".join(f"{name} ({place_counts[name]})" for name in short_places)
        )

    if problems:
        raise RuntimeError(
            "Seed-data invariant violated — " + "; ".join(problems)
        )
