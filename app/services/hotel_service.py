"""Hotel lookup over the in-memory seed data."""

from app.data.hotels import HOTELS
from app.schemas.hotel import Hotel

# Validate the seed data once at import time.
_HOTELS: list[Hotel] = [Hotel(**record) for record in HOTELS]


def list_hotels() -> list[Hotel]:
    """Return every seeded hotel."""
    return _HOTELS


def search_hotels(
    city: str,
    *,
    min_stars: int | None = None,
    max_price: float | None = None,
    amenities: list[str] | None = None,
) -> list[Hotel]:
    """Return hotels in ``city`` with optional filters.

    ``amenities`` is a list of required amenity strings — all must be present
    (case-insensitive). Unknown cities return an empty list (not a 404).
    """
    target = city.strip().lower()
    results = [hotel for hotel in _HOTELS if hotel.city.lower() == target]

    if min_stars is not None:
        results = [h for h in results if h.star_rating >= min_stars]
    if max_price is not None:
        results = [h for h in results if h.price_per_night <= max_price]
    if amenities:
        required = [a.strip().lower() for a in amenities]
        results = [
            h
            for h in results
            if all(req in [a.lower() for a in h.amenities] for req in required)
        ]

    return results


def get_hotel(hotel_id: str) -> Hotel | None:
    """Return the hotel with ``hotel_id``, or ``None`` if it does not exist."""
    return next((hotel for hotel in _HOTELS if hotel.id == hotel_id), None)
