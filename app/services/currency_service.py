"""Currency conversion over the static mock FX table (``app/data/fx.py``).

Pure and synchronous — no network. Currency codes are exact identifiers (like
IATA codes), so an unknown code is a 404; a free-text ``country`` is resolved
fuzzily and an unrecognised one simply yields no ``local_currency`` (not a 404),
consistent with how the rest of the API treats free-text locations.
"""

from app.core.text import best_match
from app.data.fx import (
    COUNTRY_CURRENCY,
    CURRENCY_NAMES,
    LAST_UPDATED,
    RATES,
)
from app.exceptions import NotFoundError
from app.schemas.currency import CurrencyConvertResponse, LocalCurrency

_VALID_CODES = sorted(RATES)
_COUNTRY_NAMES: list[str] = sorted(COUNTRY_CURRENCY)


def _resolve_code(code: str) -> str:
    """Normalise and validate an ISO 4217 code, or raise ``NotFoundError``."""
    normalised = code.strip().upper()
    if normalised not in RATES:
        raise NotFoundError(
            f"Unknown currency code '{code}'.",
            hint=f"Supported codes: {', '.join(_VALID_CODES)}.",
        )
    return normalised


def _local_currency(country: str | None) -> LocalCurrency | None:
    if not country:
        return None
    name = best_match(country, _COUNTRY_NAMES, [lambda c: c])
    if name is None:
        return None
    code = COUNTRY_CURRENCY[name]
    return LocalCurrency(code=code, name=CURRENCY_NAMES[code])


def convert(
    from_code: str,
    to_code: str,
    amount: float,
    country: str | None = None,
) -> CurrencyConvertResponse:
    """Convert ``amount`` from one currency to another using the mock table."""
    src = _resolve_code(from_code)
    dst = _resolve_code(to_code)

    rate = RATES[dst] / RATES[src]
    return CurrencyConvertResponse(
        from_currency=src,
        to_currency=dst,
        rate=round(rate, 6),
        amount=amount,
        converted=round(amount * rate, 2),
        last_updated=LAST_UPDATED,
        local_currency=_local_currency(country),
    )
