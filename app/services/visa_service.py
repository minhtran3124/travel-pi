"""Visa / entry-requirement lookup over DB-backed seed data.

Pure and synchronous — no network. Free-text ``city``/``country`` resolve
fuzzily via ``core/text.best_match`` (a city resolves its own country, like
``tip_service``); an unrecognised location yields ``found: False`` with no
``entry`` — never a 404, consistent with the rest of the API's free-text
location handling.

The visa records, city list, and country list live in the database now; the
repos return raw data and the fuzzy resolution stays here in the service.
"""

from app.core.config import get_settings
from app.core.text import best_match
from app.crud.city import CityRepository
from app.crud.country import CountryRepository
from app.crud.visa import VisaRepository
from app.db.engine import get_session_factory
from app.schemas.visa import VisaResponse

DISCLAIMER = (
    "General guidance only and dependent on your nationality — always confirm "
    "current requirements with the destination's official immigration authority "
    "or embassy before you travel."
)

# Module-level repo singletons, built from the configured DB. Not FastAPI
# dependencies, so tests repoint them via the setters after seeding the temp DB.
_settings_url = get_settings().database_url
_visa_repo = VisaRepository(get_session_factory(_settings_url))
_city_repo = CityRepository(get_session_factory(_settings_url))
_country_repo = CountryRepository(get_session_factory(_settings_url))


def set_visa_repo(repo: VisaRepository) -> None:
    """Point visa reads at a different store — used by tests."""
    global _visa_repo
    _visa_repo = repo


def set_city_repo(repo: CityRepository) -> None:
    """Point city reads at a different store — used by tests."""
    global _city_repo
    _city_repo = repo


def set_country_repo(repo: CountryRepository) -> None:
    """Point country reads at a different store — used by tests."""
    global _country_repo
    _country_repo = repo


def get_visa(
    *,
    city: str | None = None,
    country: str | None = None,
) -> VisaResponse:
    """Return entry-requirement guidance for a destination.

    Exactly one of ``city`` or ``country`` drives the lookup (city takes
    precedence and resolves its own country). Both are matched fuzzily. The
    caller is responsible for rejecting the case where neither is provided.
    """
    resolved_country: str | None = None
    resolved_city: str | None = None

    if city:
        name = best_match(city, _city_repo.distinct_names(), [lambda c: c])
        if name is not None:
            record = _city_repo.get(name)
            if record is not None:
                resolved_city = record.name
                resolved_country = record.country
    elif country:
        resolved_country = best_match(
            country, _country_repo.distinct_names(), [lambda c: c]
        )

    entry = _visa_repo.get(resolved_country) if resolved_country else None

    return VisaResponse(
        city=resolved_city,
        country=resolved_country or (country or city or ""),
        found=entry is not None,
        entry=entry,
        disclaimer=DISCLAIMER,
    )
