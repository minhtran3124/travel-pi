"""Place / attraction lookup over in-memory seed data."""

from app.data.places import PLACES
from app.schemas.place import Place

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
        target = city.strip().lower()
        results = [p for p in results if p.city.lower() == target]
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
