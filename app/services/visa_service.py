"""Visa / entry-requirement lookup over static seed data (``app/data/visa.py``).

Pure and synchronous — no network. Free-text ``city``/``country`` resolve
fuzzily via ``core/text.best_match`` (a city resolves its own country, like
``tip_service``); an unrecognised location yields ``found: False`` with no
``entry`` — never a 404, consistent with the rest of the API's free-text
location handling.
"""

from app.core.text import best_match
from app.data.cities import CITIES
from app.data.visa import COUNTRY_VISA
from app.schemas.visa import EntryRequirements, VisaResponse

DISCLAIMER = (
    "General guidance only and dependent on your nationality — always confirm "
    "current requirements with the destination's official immigration authority "
    "or embassy before you travel."
)

_ALL_CITIES: list[dict] = list(CITIES)
_ALL_COUNTRIES: list[str] = sorted({c["country"] for c in CITIES})


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
        record = best_match(city, _ALL_CITIES, [lambda c: c["name"]])
        if record is not None:
            resolved_city = record["name"]
            resolved_country = record["country"]
    elif country:
        resolved_country = best_match(country, _ALL_COUNTRIES, [lambda c: c])

    visa = COUNTRY_VISA.get(resolved_country) if resolved_country else None
    entry = EntryRequirements(**visa) if visa is not None else None

    return VisaResponse(
        city=resolved_city,
        country=resolved_country or (country or city or ""),
        found=entry is not None,
        entry=entry,
        disclaimer=DISCLAIMER,
    )
