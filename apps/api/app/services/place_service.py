"""Place / attraction lookup over the DB-backed seed data — the repo does exact/range SQL filters; fuzzy city resolution and the result sort stay here in the service."""

import re
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.geo import haversine_km
from app.core.text import best_match
from app.db.session import get_session
from app.exceptions import NotFoundError
from app.repositories.place_ref import PlaceRepository
from app.repositories.saved_place import SavedPlaceRepository
from app.schemas.place import NearbyPlace, ParsedQuery, Place, PlaceCategoryInfo
from app.schemas.saved_place import SavedPlace

# Valid sort keys live in app.enums.PlaceSort; dispatch is the if/elif in search_places.
DEFAULT_SORT = "rating_desc"

# Per-category (color, icon) display metadata, mirroring the dashboard palette so both share one source of truth; unmapped categories fall back to _FALLBACK.
CATEGORY_META: dict[str, tuple[str, str]] = {
    "attraction": ("#38bdf8", "camera"),
    "restaurant": ("#fb923c", "utensils"),
    "cafe": ("#fbbf24", "coffee"),
    "activity": ("#34d399", "ticket"),
    "nightlife": ("#f87171", "wine"),
    "shopping": ("#c4b5fd", "shopping-bag"),
}
_FALLBACK: tuple[str, str] = ("#94a3b8", "map-pin")


class PlaceService:
    """Place / attraction lookup bound to the request session."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._place = PlaceRepository(session)

    def categories(self) -> list[PlaceCategoryInfo]:
        """Distinct place categories enriched with display metadata, sorted by name."""
        return [
            PlaceCategoryInfo(
                name=name,
                color=CATEGORY_META.get(name, _FALLBACK)[0],
                icon=CATEGORY_META.get(name, _FALLBACK)[1],
            )
            for name in self._place.distinct_categories()
        ]

    def cities(self) -> list[str]:
        """Distinct place cities, sorted."""
        return self._place.distinct_cities()

    def list_places(self) -> list[Place]:
        return self._place.all()

    def resolve_city(self, name: str | None) -> str | None:
        """Resolve a free-text city name to a canonical city that has places, fuzzily; ``None`` if nothing matches."""
        return best_match(name, self._place.distinct_cities(), [lambda c: c])

    def resolve_category(self, name: str | None) -> str | None:
        """Resolve a free-text category to a canonical one (e.g. "cafes" → "cafe"); ``None`` if nothing matches."""
        return best_match(name, CATEGORY_META.keys(), [lambda c: c])

    def search_places(
        self,
        *,
        city: str | None = None,
        category: str | None = None,
        min_rating: float | None = None,
        price_level: int | None = None,
        price_level_max: int | None = None,
        recommended_only: bool = False,
        sort: str = DEFAULT_SORT,
        exclude_names: list[str] | None = None,
    ) -> list[Place]:
        """Filter and sort places; ``price_level`` matches a band exactly while ``price_level_max`` is a ceiling (``<=``) for NL budget queries."""
        if city:
            # A given-but-unrecognised city yields no results (not all places).
            resolved = self.resolve_city(city)
            if not resolved:
                return []
        else:
            resolved = None

        if category:
            # Same given-but-unrecognised contract as city (e.g. "cafes" → "cafe").
            resolved_category = self.resolve_category(category)
            if not resolved_category:
                return []
        else:
            resolved_category = None

        results = self._place.search(
            city=resolved,
            category=resolved_category,
            min_rating=min_rating,
            price_level=price_level,
            price_level_max=price_level_max,
            recommended=recommended_only or None,
        )

        if exclude_names:
            excluded = set(exclude_names)
            results = [p for p in results if p.name not in excluded]

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

    def get_place(self, place_id: str) -> Place | None:
        """Return the place by raw ID or its friendly ``PLC-XXXXXX`` short code (case-insensitive); ``None`` if nothing matches."""
        if not place_id:
            return None
        normalised = place_id.strip()
        if normalised.upper().startswith("PLC-"):
            return self._place.by_short_code(normalised)
        return self._place.get(normalised)

    def resolve(
        self, place_id: str, source: str, user_id: str | None = None
    ) -> Place | SavedPlace | None:
        """Resolve a shortlisted place; ``source`` is 'catalog' | 'saved'. The ``saved`` lookup is scoped to ``user_id`` (``None`` = unscoped, trusted callers) so a user-controlled id can never read another user's saved place; ``None`` on a miss."""
        if source == "saved":
            return SavedPlaceRepository(self._session).get(place_id, user_id=user_id)
        return self.get_place(place_id)

    def nearby_places(
        self,
        place_id: str,
        *,
        radius_km: float = 5.0,
        limit: int = 10,
        category: str | None = None,
    ) -> tuple[Place, list[NearbyPlace]]:
        """Return places within ``radius_km`` of ``place_id``, nearest-first; raises :class:`NotFoundError` if the origin is unknown or has no coordinates."""
        origin = self.get_place(place_id)
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
        for place in self._place.all():
            if (
                place.id == origin.id
                or place.latitude is None
                or place.longitude is None
            ):
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

    # --- Natural-language query parsing (POST /places/search/nl) --------------

    def _nl_city(self, query: str) -> str | None:
        """Longest canonical city name appearing in the query (case-insensitive), or ``None``."""
        hits = [c for c in self.cities() if c.lower() in query]
        return max(hits, key=len) if hits else None

    def parse_nl_query(self, query: str) -> ParsedQuery:
        """Parse a free-text places query into structured filters via keyword/regex extraction; unrecognised words are ignored and the returned city is canonical."""
        q = query.lower()
        return ParsedQuery(
            city=self._nl_city(q),
            category=_nl_category(q),
            min_rating=_nl_min_rating(q),
            price_level=_nl_price_level(q),
        )


def get_place_service(
    session: Annotated[Session, Depends(get_session)],
) -> PlaceService:
    """FastAPI dependency: a place service bound to the request session."""
    return PlaceService(session)


# --- Natural-language parsing tables / helpers (pure, repo-free) --------------

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
# "4 star", "4.5 stars", "4+ star" → capture the rating (multi-digit captured whole, clamped to 5.0 downstream).
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
