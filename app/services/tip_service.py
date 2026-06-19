"""Local-tips lookup over the DB-backed seed data.

Tip records are read through ``tip_repo`` (``app.crud.tip``) per request;
``app/data/tips.py`` remains the guarded seed source. Country tips are
inherited by every city in that country; city tips are merged on top when a
``city`` is queried. Unknown locations return an empty tip list
(``count: 0``), never a 404 — consistent with hotels/places.

Positional tip ids (``tip_{scope}_{prefix}_{NN}``) are produced by the seeder
and ordered by ``position`` in the repo, so they are reproduced verbatim.
``get_all_tips`` keeps assembling the merged list HERE (iterating the same
country/city key order as before and attaching the presentation ``location``
label) — the repo's ``all_tips`` is NOT used (its order is inverted and it
carries no ``location``).
"""

from app.core.config import get_settings
from app.core.text import best_match
from app.crud.city import CityRepository
from app.crud.country import CountryRepository
from app.crud.tip import TipRepository
from app.db.engine import get_session_factory
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

# Tips / cities / countries are DB-backed. The repos are built from the
# configured DB at import time; they are NOT FastAPI dependencies, so tests
# repoint them via the setters after seeding the temp DB (see tests/conftest.py).
_db_url = get_settings().database_url
_tip_repo = TipRepository(get_session_factory(_db_url))
_city_repo = CityRepository(get_session_factory(_db_url))
_country_repo = CountryRepository(get_session_factory(_db_url))


def set_tip_repo(repo: TipRepository) -> None:
    """Point tip reads at a different store — used by tests to read the seeded
    temporary database instead of the real travel.db."""
    global _tip_repo
    _tip_repo = repo


def set_city_repo(repo: CityRepository) -> None:
    """Point city reads at a different store (city resolution + iteration)."""
    global _city_repo
    _city_repo = repo


def set_country_repo(repo: CountryRepository) -> None:
    """Point country reads at a different store (country-name resolution)."""
    global _country_repo
    _country_repo = repo


def _resolve_tips(
    scope: str, key: str, *, location_label: str | None = None
) -> list[Tip]:
    """Fetch tips for one ``(scope, key)`` and attach the presentation label.

    The repo returns tips ordered by ``position`` with stable ids; this sets the
    optional ``location`` field used by the dashboard's mixed-destination view.
    """
    tips = _tip_repo.for_location(scope, key)
    if location_label is not None:
        for t in tips:
            t.location = location_label
    return tips


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

    all_cities = _city_repo.list_with_counts()

    if city:
        record = best_match(city, all_cities, [lambda c: c.name])
        if record is not None:
            resolved_city = record.name
            resolved_country = record.country
            tips += _resolve_tips("city", resolved_city)
    elif country:
        countries = sorted({c.country for c in all_cities})
        resolved_country = best_match(country, countries, [lambda c: c])

    if resolved_country is not None:
        tips += _resolve_tips("country", resolved_country)

    if category:
        cat = category.strip().lower()
        tips = [t for t in tips if t.category == cat]
    if essential_only:
        tips = [t for t in tips if t.is_essential]

    summary = (
        _tip_repo.country_summary(resolved_country)
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

    The assembly stays in the service (not ``tip_repo.all_tips``) so the merge
    order — every country first (alphabetical by name), then every city in seed
    order — and the ``location`` labels match the previous behaviour exactly.
    """
    tips: list[Tip] = []

    all_cities = _city_repo.list_with_counts()
    all_countries = sorted({c.country for c in all_cities})

    for country_name in all_countries:
        tips += _resolve_tips("country", country_name, location_label=country_name)

    for city in all_cities:
        city_tips = _resolve_tips(
            "city",
            city.name,
            location_label=f"{city.name} · {city.country}",
        )
        tips += city_tips

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
