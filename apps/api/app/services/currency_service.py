"""Currency conversion over the DB-backed FX table (pure, synchronous, no network).

Unknown code → 404; unrecognised free-text country → no ``local_currency`` (not a 404).
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.text import best_match
from app.data.countries import resolve_country_alias
from app.db.session import get_session
from app.exceptions import NotFoundError
from app.repositories.fx import FxRepository
from app.schemas.currency import CurrencyConvertResponse, LocalCurrency


class CurrencyService:
    """Currency conversion over the DB-backed FX table."""

    def __init__(self, session: Session) -> None:
        self._fx = FxRepository(session)

    def _resolve_code(self, code: str) -> str:
        """Normalise and validate an ISO 4217 code, or raise ``NotFoundError``."""
        normalised = code.strip().upper()
        if self._fx.rate(normalised) is None:
            raise NotFoundError(
                f"Unknown currency code '{code}'.",
                hint=f"Supported codes: {', '.join(self._fx.valid_codes())}.",
            )
        return normalised

    def _local_currency(self, country: str | None) -> LocalCurrency | None:
        if not country:
            return None
        name = resolve_country_alias(country) or best_match(
            country, self._fx.country_names(), [lambda c: c]
        )
        if name is None:
            return None
        code = self._fx.country_currency(name)
        if code is None:
            return None
        return LocalCurrency(code=code, name=self._fx.name(code))

    def convert(
        self,
        from_code: str,
        to_code: str,
        amount: float,
        country: str | None = None,
    ) -> CurrencyConvertResponse:
        """Convert ``amount`` from one currency to another using the mock table."""
        src = self._resolve_code(from_code)
        dst = self._resolve_code(to_code)

        rate = self._fx.rate(dst) / self._fx.rate(src)
        return CurrencyConvertResponse(
            from_currency=src,
            to_currency=dst,
            rate=round(rate, 6),
            amount=amount,
            converted=round(amount * rate, 2),
            last_updated=self._fx.last_updated(),
            local_currency=self._local_currency(country),
        )


def get_currency_service(
    session: Annotated[Session, Depends(get_session)],
) -> CurrencyService:
    """FastAPI dependency: a currency service bound to the request session."""
    return CurrencyService(session)
