"""Place / attraction lookup over in-memory seed data."""

from app.core.geo import haversine_km
from app.core.text import best_match
from app.data.places import PLACES
from app.exceptions import NotFoundError
from app.schemas.place import NearbyPlace, Place

_PLACES: list[Place] = [Place(**record) for record in PLACES]

CATEGORIES = sorted({p.category for p in _PLACES})
CITIES = sorted({p.city for p in _PLACES})


def _build_short_code_index(places: list[Place]) -> dict[str, Place]:
    """Map ``short_code -> Place``, failing fast on collisions (see hotel_service)."""
    index: dict[str, Place] = {}
    for place in places:
        existing = index.get(place.short_code)
        if existing is not None:
            raise RuntimeError(
                f"Place short-code collision: {place.short_code} maps to "
                f"both {existing.id!r} and {place.id!r}"
            )
        index[place.short_code] = place
    return index


_PLACES_BY_SHORT_CODE: dict[str, Place] = _build_short_code_index(_PLACES)

# Valid sort keys live in ``app.enums.PlaceSort`` (the JSON router validates
# against the enum). The actual sort dispatch happens via the if/elif chain
# in ``search_places`` below.
DEFAULT_SORT = "rating_desc"


def list_places() -> list[Place]:
    return list(_PLACES)


def resolve_city(name: str | None) -> str | None:
    """Resolve a free-text city name to a canonical city that has places.

    Typo/spacing/case tolerant (e.g. "danang" → "Da Nang"), using the same
    matcher as ``GET /cities?q=``. Returns ``None`` if nothing matches.
    """
    return best_match(name, CITIES, [lambda c: c])


def search_places(
    *,
    city: str | None = None,
    category: str | None = None,
    min_rating: float | None = None,
    price_level: int | None = None,
    recommended_only: bool = False,
    sort: str = DEFAULT_SORT,
) -> list[Place]:
    results = list(_PLACES)

    if city:
        # A given-but-unrecognised city yields no results (not all places).
        resolved = resolve_city(city)
        results = [p for p in results if p.city == resolved] if resolved else []
    if category:
        cat = category.strip().lower()
        results = [p for p in results if p.category.lower() == cat]
    if min_rating is not None:
        results = [p for p in results if p.rating >= min_rating]
    if price_level is not None:
        results = [p for p in results if p.price_level == price_level]
    if recommended_only:
        results = [p for p in results if p.is_recommended]

    if sort == "rating_asc":
        results.sort(key=lambda p: p.rating)
    elif sort == "name":
        results.sort(key=lambda p: p.name.lower())
    elif sort == "price_asc":
        results.sort(key=lambda p: p.price_level)
    elif sort == "price_desc":
        results.sort(key=lambda p: -p.price_level)
    elif sort == "reviews_desc":
        results.sort(key=lambda p: -p.review_count)
    else:
        results.sort(key=lambda p: -p.rating)

    return results


def get_place(place_id: str) -> Place | None:
    """Return the place by raw ID *or* its friendly ``PLC-XXXXXX`` short code.

    The short-code lookup is case-insensitive (``plc-ab23xy`` is the same as
    ``PLC-AB23XY``). Returns ``None`` if nothing matches.
    """
    if not place_id:
        return None
    normalised = place_id.strip()
    if normalised.upper().startswith("PLC-"):
        return _PLACES_BY_SHORT_CODE.get(normalised.upper())
    return next((p for p in _PLACES if p.id == normalised), None)


def nearby_places(
    place_id: str,
    *,
    radius_km: float = 5.0,
    limit: int = 10,
    category: str | None = None,
) -> tuple[Place, list[NearbyPlace]]:
    """Return places within ``radius_km`` of ``place_id``, nearest-first.

    Excludes the origin place itself and any place missing coordinates.
    ``category`` optionally narrows the result to one category. Raises
    :class:`NotFoundError` if the origin place is unknown or has no
    coordinates.
    """
    origin = get_place(place_id)
    if origin is None:
        raise NotFoundError(
            f"Place '{place_id}' not found",
            hint=(
                "Use GET /places/search?city=<city> to find a valid "
                "place_id (or pass the short PLC-XXXX code)."
            ),
        )
    if origin.latitude is None or origin.longitude is None:
        raise NotFoundError(
            f"Place '{place_id}' has no coordinates",
            hint=(
                "This place is missing latitude/longitude in the seed data "
                "and cannot anchor a nearby search."
            ),
        )

    wanted = category.strip().lower() if category else None
    found: list[NearbyPlace] = []
    for place in _PLACES:
        if place.id == origin.id or place.latitude is None or place.longitude is None:
            continue
        if wanted and place.category.lower() != wanted:
            continue
        distance = haversine_km(
            origin.latitude, origin.longitude, place.latitude, place.longitude
        )
        if distance <= radius_km:
            found.append(
                NearbyPlace(**place.model_dump(), distance_km=round(distance, 2))
            )

    found.sort(key=lambda np: np.distance_km)
    return origin, found[:limit]
