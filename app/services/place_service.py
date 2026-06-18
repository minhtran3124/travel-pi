"""Place / attraction lookup over in-memory seed data."""

import re

from app.core.geo import haversine_km
from app.core.text import best_match
from app.data.places import PLACES
from app.exceptions import NotFoundError
from app.schemas.place import NearbyPlace, ParsedQuery, Place
from app.schemas.saved_place import SavedPlace

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
    price_level_max: int | None = None,
    recommended_only: bool = False,
    sort: str = DEFAULT_SORT,
) -> list[Place]:
    """Filter and sort places.

    ``price_level`` matches a band exactly; ``price_level_max`` is a ceiling
    (``<=``) used by the NL search shim so a budget like "under $40" includes
    everything at or below that band. They may be combined but normally only
    one is supplied.
    """
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
    if price_level_max is not None:
        results = [p for p in results if p.price_level <= price_level_max]
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


def resolve(place_id: str, source: str) -> Place | SavedPlace | None:
    """Resolve a shortlisted place to its body. ``source``: 'catalog' | 'saved'.

    Returns ``None`` when the place is unknown (catalog miss, or a missing /
    soft-deleted saved place). The ``saved`` branch imports the saved-place
    service lazily to avoid a circular import (place_service ↔
    saved_place_service).
    """
    if source == "saved":
        from app.services.saved_place_service import get_saved_place_service

        return get_saved_place_service()._repo.get(place_id)
    return get_place(place_id)


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


# --- Natural-language query parsing (POST /places/search/nl) ------------------
# Pure keyword/regex extraction — no LLM. The caller gets the parsed filters
# echoed back so a small model can see how its query was interpreted.

# Category inferred from keywords; checked in order, first hit wins.
_NL_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    (
        "restaurant",
        (
            "restaurant",
            "dinner",
            "lunch",
            "breakfast",
            "brunch",
            "dining",
            "dine",
            "eat",
            "food",
            "meal",
        ),
    ),
    ("cafe", ("cafe", "café", "coffee", "espresso", "tea")),
    ("nightlife", ("nightlife", "bar", "club", "pub", "drinks", "cocktail")),
    ("shopping", ("shopping", "shop", "mall", "market", "store", "boutique")),
    ("activity", ("activity", "tour", "adventure", "experience", "workshop", "class")),
    (
        "attraction",
        (
            "attraction",
            "sight",
            "sightseeing",
            "museum",
            "temple",
            "landmark",
            "gallery",
            "park",
            "visit",
        ),
    ),
]

# Price band inferred from adjective keywords; checked in order.
_NL_PRICE_KEYWORDS: list[tuple[int, tuple[str, ...]]] = [
    (1, ("cheap", "budget", "free", "affordable", "inexpensive")),
    (2, ("moderate", "mid-range", "midrange", "reasonable")),
    (3, ("expensive", "pricey", "upscale")),
    (4, ("luxury", "luxurious", "fancy", "high-end", "fine dining")),
]

# "under $40", "$40", "under 40" → capture the dollar amount.
_NL_BUDGET_RE = re.compile(r"\$\s*(\d+(?:\.\d+)?)|under\s+(\d+(?:\.\d+)?)")
# "4 star", "4.5 stars", "4+ star" → capture the rating. Multi-digit values
# (e.g. "10 star") are captured whole and clamped to 5.0 by _nl_min_rating,
# rather than mis-parsing the trailing single digit.
_NL_STAR_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*stars?")
_NL_TOP_RATED = ("highly rated", "top-rated", "top rated", "highest rated", "best")


def _budget_to_price_level(amount: float) -> int:
    """Map a max-dollar budget to a single price band (1–4)."""
    if amount <= 20:
        return 1
    if amount <= 50:
        return 2
    if amount <= 100:
        return 3
    return 4


def _nl_has_word(query: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", query) is not None


def _nl_city(query: str) -> str | None:
    """Longest canonical city name appearing in the query (case-insensitive)."""
    hits = [c for c in CITIES if c.lower() in query]
    return max(hits, key=len) if hits else None


def _nl_category(query: str) -> str | None:
    for category, words in _NL_CATEGORY_KEYWORDS:
        if any(_nl_has_word(query, w) for w in words):
            return category
    return None


def _nl_price_level(query: str) -> int | None:
    budget = _NL_BUDGET_RE.search(query)
    if budget:
        return _budget_to_price_level(float(budget.group(1) or budget.group(2)))
    for level, words in _NL_PRICE_KEYWORDS:
        if any(_nl_has_word(query, w) for w in words):
            return level
    return None


def _nl_min_rating(query: str) -> float | None:
    star = _NL_STAR_RE.search(query)
    if star:
        return max(0.0, min(5.0, float(star.group(1))))
    if any(phrase in query for phrase in _NL_TOP_RATED):
        return 4.5
    return None


def parse_nl_query(query: str) -> ParsedQuery:
    """Parse a free-text places query into structured filters.

    Pure keyword/regex extraction over the lowercased query. Unrecognised
    words are ignored; any field with no signal comes back ``None``. The
    returned city is the canonical name (e.g. "Hanoi"), so it feeds straight
    into :func:`search_places`.
    """
    q = query.lower()
    return ParsedQuery(
        city=_nl_city(q),
        category=_nl_category(q),
        min_rating=_nl_min_rating(q),
        price_level=_nl_price_level(q),
    )
