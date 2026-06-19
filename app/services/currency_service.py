"""Currency conversion over the DB-backed FX table (seeded from ``app/data/fx.py``).

Pure and synchronous — no network. Currency codes are exact identifiers (like
IATA codes), so an unknown code is a 404; a free-text ``country`` is resolved
fuzzily and an unrecognised one simply yields no ``local_currency`` (not a 404),
consistent with how the rest of the API treats free-text locations.

The FX rows live in the database now; the repo returns raw values and the 404
policy + fuzzy country resolution stay here in the service.
"""

from app.core.config import get_settings
from app.core.text import best_match
from app.crud.fx import FxRepository
from app.db.engine import get_session_factory
from app.exceptions import NotFoundError
from app.schemas.currency import CurrencyConvertResponse, LocalCurrency

# Module-level repo singleton, built from the configured DB. Not a FastAPI
# dependency, so tests repoint it via ``set_fx_repo`` after seeding the temp DB.
_fx_repo = FxRepository(get_session_factory(get_settings().database_url))


def set_fx_repo(repo: FxRepository) -> None:
    """Point FX reads at a different store — used by tests to read the seeded
    temporary database instead of the real travel.db."""
    global _fx_repo
    _fx_repo = repo


def _resolve_code(code: str) -> str:
    """Normalise and validate an ISO 4217 code, or raise ``NotFoundError``."""
    normalised = code.strip().upper()
    if _fx_repo.rate(normalised) is None:
        raise NotFoundError(
            f"Unknown currency code '{code}'.",
            hint=f"Supported codes: {', '.join(_fx_repo.valid_codes())}.",
        )
    return normalised


def _local_currency(country: str | None) -> LocalCurrency | None:
    if not country:
        return None
    name = best_match(country, _fx_repo.country_names(), [lambda c: c])
    if name is None:
        return None
    code = _fx_repo.country_currency(name)
    if code is None:
        return None
    return LocalCurrency(code=code, name=_fx_repo.name(code))


def convert(
    from_code: str,
    to_code: str,
    amount: float,
    country: str | None = None,
) -> CurrencyConvertResponse:
    """Convert ``amount`` from one currency to another using the mock table."""
    src = _resolve_code(from_code)
    dst = _resolve_code(to_code)

    rate = _fx_repo.rate(dst) / _fx_repo.rate(src)
    return CurrencyConvertResponse(
        from_currency=src,
        to_currency=dst,
        rate=round(rate, 6),
        amount=amount,
        converted=round(amount * rate, 2),
        last_updated=_fx_repo.last_updated(),
        local_currency=_local_currency(country),
    )
