"""Place / attraction lookup over in-memory seed data."""

from app.core.geo import haversine_km
from app.core.text import best_match
from app.data.places import PLACES
from app.exceptions import NotFoundError
from app.schemas.place import NearbyPlace, Place

_PLACES: list[Place] = [Place(**record) for record in PLACES]

CATEGORIES = sorted({p.category for p in _PLACES})
CITIES = sorted({p.city for p in _PLACES})

_SORTS: dict[str, str | None] = {
    "rating_desc": None,  # default — handled below
    "rating_asc": None,
    "name": None,
    "price_asc": None,
    "price_desc": None,
    "reviews_desc": None,
}

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
    return next((p for p in _PLACES if p.id == place_id), None)


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
        raise NotFoundError(f"Place '{place_id}' not found")
    if origin.latitude is None or origin.longitude is None:
        raise NotFoundError(f"Place '{place_id}' has no coordinates")

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
