"""Hotel lookup + deterministic availability over the DB-backed seed data — availability is generated from a hashed (hotel + date range) query, never stored."""

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
    """Number of nights between two YYYY-MM-DD dates; raises ``ValueError`` unless ``check_out`` is strictly after ``check_in`` (a prior clamp-to-1 silently booked a paid stay)."""
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
    """Deterministic rooms free for a date range (0..``total_rooms``; 0 = fully booked)."""
    seed = hashlib.md5(f"{hotel.id}-{check_in}-{check_out}".encode()).hexdigest()
    return Random(seed).randint(0, total_rooms(hotel))


def is_available(
    hotel: Hotel, check_in: str, check_out: str, *, rooms: int, guests: int
) -> bool:
    """Whether ``hotel`` can take the booking: enough rooms free and the requested rooms can physically hold the party."""
    free = available_rooms(hotel, check_in, check_out)
    return free >= rooms and max_occupancy(hotel) * rooms >= guests


class HotelService:
    """Hotel lookup + deterministic availability over the DB-backed seed data."""

    def __init__(self, session: Session) -> None:
        self._hotel_repo = HotelRepository(session)

    def list_hotels(self) -> list[Hotel]:
        """Return every seeded hotel."""
        return self._hotel_repo.all()

    def resolve_city(self, name: str | None) -> str | None:
        """Resolve a free-text city name to a canonical hotel city, fuzzily (typo/spacing/case tolerant); ``None`` if nothing matches."""
        return best_match(name, self._hotel_repo.distinct_cities(), [lambda c: c])

    def resolve_amenities(self, amenities: list[str] | None) -> list[str] | None:
        """Fuzzy-resolve each amenity to its canonical seeded string; an unmatched amenity is passed through as-is so it excludes every hotel rather than silently guessing."""
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
        """Return hotels in ``city`` (matched fuzzily) with optional filters; an unrecognised city returns an empty list, not a 404."""
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
        """Return the hotel by raw ID or its friendly ``HTL-XXXXXX`` short code (case-insensitive); ``None`` if neither matches."""
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
        """Return ``(nights, results)`` — hotels matching ``city``/filters, each annotated with availability and the all-in ``total_price``; ``nights`` is returned even when ``results`` is empty."""
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
    """FastAPI dependency: a hotel service bound to the request session."""
    return HotelService(session)
