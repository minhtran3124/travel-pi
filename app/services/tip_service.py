"""Local-tips lookup over in-memory seed data.

Country tips are inherited by every city in that country; city tips are
merged on top when a ``city`` is queried. Unknown locations return an empty
tip list (``count: 0``), never a 404 — consistent with hotels/places.
"""

from app.core.text import best_match
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

# Resolution targets, built once at import: every city record, and the
# distinct country names. Both ``city`` and ``country`` query params are
# matched fuzzily against these (typo/spacing/case tolerant).
_ALL_CITIES: list[dict] = list(CITIES)
_ALL_COUNTRIES: list[str] = sorted({c["country"] for c in CITIES})


def _slug(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text.lower())


def _build_tips(
    records: list[dict],
    scope: str,
    location: str,
    *,
    location_label: str | None = None,
) -> list[Tip]:
    """Turn raw seed dicts into ``Tip`` objects with stable, positional IDs.

    ``location_label`` is the human-friendly "where" attached to each tip
    (e.g. ``"Hanoi · Vietnam"``). It is only set by callers that mix tips
    from many destinations into one list (the dashboard's "all" view); the
    standard per-destination lookup leaves it ``None`` since the caller
    already named the location.
    """
    prefix = _slug(location)
    return [
        Tip(
            id=f"tip_{scope}_{prefix}_{i:02d}",
            scope=scope,
            category=r["category"],
            title=r["title"],
            content=r["content"],
            is_essential=r.get("is_essential", False),
            location=location_label,
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
    precedence and resolves its own country). Both are matched fuzzily — a
    typo or partial name still resolves. Caller is responsible for rejecting
    the case where neither is provided.
    """
    resolved_country: str | None = None
    resolved_city: str | None = None
    tips: list[Tip] = []

    if city:
        record = best_match(city, _ALL_CITIES, [lambda c: c["name"]])
        if record is not None:
            resolved_city = record["name"]
            resolved_country = record["country"]
            tips += _build_tips(CITY_TIPS.get(resolved_city, []), "city", resolved_city)
    elif country:
        resolved_country = best_match(country, _ALL_COUNTRIES, [lambda c: c])

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


def get_all_tips(
    *,
    category: str | None = None,
    essential_only: bool = False,
) -> TipsResponse:
    """Return every tip across every country and city, with location set.

    Used by the dashboard's "show me everything" landing view — the JSON API
    keeps requiring a country or city, this just merges the same seed data
    into one flat list. Each tip carries its ``location`` (``"Hanoi · Vietnam"``
    for city scope, ``"Vietnam"`` for country scope) so the UI can label cards
    when destinations are mixed.
    """
    tips: list[Tip] = []

    for country_name in _ALL_COUNTRIES:
        tips += _build_tips(
            COUNTRY_TIPS.get(country_name, []),
            "country",
            country_name,
            location_label=country_name,
        )

    for city in _ALL_CITIES:
        city_records = CITY_TIPS.get(city["name"], [])
        if not city_records:
            continue
        tips += _build_tips(
            city_records,
            "city",
            city["name"],
            location_label=f"{city['name']} · {city['country']}",
        )

    if category:
        cat = category.strip().lower()
        tips = [t for t in tips if t.category == cat]
    if essential_only:
        tips = [t for t in tips if t.is_essential]

    return TipsResponse(
        city=None,
        country="",  # No single destination — empty so the template hides the summary header.
        count=len(tips),
        summary="",
        tips=tips,
    )
