"""Local-tips lookup over in-memory seed data.

Country tips are inherited by every city in that country; city tips are
merged on top when a ``city`` is queried. Unknown locations return an empty
tip list (``count: 0``), never a 404 — consistent with hotels/places.
"""

from app.data.cities import CITIES
from app.data.tips import CITY_TIPS, COUNTRY_SUMMARIES, COUNTRY_TIPS
from app.schemas.tip import Tip, TipsResponse

VALID_CATEGORIES = {
    "transport",
    "money",
    "safety",
    "culture",
    "food",
    "connectivity",
    "health",
    "etiquette",
    "best_time",
    "language",
}

# Lower-cased lookup tables built once at import.
_COUNTRY_BY_LOWER: dict[str, str] = {c["country"].lower(): c["country"] for c in CITIES}
_CITY_BY_LOWER: dict[str, dict] = {c["name"].lower(): c for c in CITIES}


def _slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text.lower())


def _build_tips(records: list[dict], scope: str, location: str) -> list[Tip]:
    """Turn raw seed dicts into ``Tip`` objects with stable, positional IDs."""
    prefix = _slug(location)
    return [
        Tip(
            id=f"tip_{scope}_{prefix}_{i:02d}",
            scope=scope,
            category=r["category"],
            title=r["title"],
            content=r["content"],
            is_essential=r.get("is_essential", False),
        )
        for i, r in enumerate(records)
    ]


def get_tips(
    *,
    city: str | None = None,
    country: str | None = None,
    category: str | None = None,
    essential_only: bool = False,
) -> TipsResponse:
    """Return merged country + city tips for a destination.

    Exactly one of ``city`` or ``country`` drives the lookup (city takes
    precedence and resolves its own country). Caller is responsible for
    rejecting the case where neither is provided.
    """
    resolved_country: str | None = None
    resolved_city: str | None = None
    tips: list[Tip] = []

    if city:
        record = _CITY_BY_LOWER.get(city.strip().lower())
        if record is not None:
            resolved_city = record["name"]
            resolved_country = record["country"]
            tips += _build_tips(CITY_TIPS.get(resolved_city, []), "city", resolved_city)
    elif country:
        resolved_country = _COUNTRY_BY_LOWER.get(country.strip().lower())

    if resolved_country is not None:
        tips += _build_tips(
            COUNTRY_TIPS.get(resolved_country, []), "country", resolved_country
        )

    if category:
        cat = category.strip().lower()
        tips = [t for t in tips if t.category == cat]
    if essential_only:
        tips = [t for t in tips if t.is_essential]

    summary = (
        COUNTRY_SUMMARIES.get(resolved_country, "")
        if resolved_country is not None
        else ""
    )

    return TipsResponse(
        city=resolved_city,
        country=resolved_country or (country or city or ""),
        count=len(tips),
        summary=summary,
        tips=tips,
    )
