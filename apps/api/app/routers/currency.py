"""Currency conversion endpoint — mock FX, no live rates."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.routers.tags import Tags
from app.schemas.currency import CurrencyConvertResponse
from app.schemas.error import error_responses
from app.services.currency_service import CurrencyService, get_currency_service

router = APIRouter(prefix="/currency", tags=[Tags.currency])

CurrencyDep = Annotated[CurrencyService, Depends(get_currency_service)]


@router.get(
    "/convert",
    response_model=CurrencyConvertResponse,
    summary="Convert an amount between currencies (mock FX)",
    responses=error_responses(404, 422),
)
def convert_currency(
    currency: CurrencyDep,
    to: Annotated[
        str,
        Query(
            description="Target ISO 4217 code (exact, case-insensitive).",
            examples=["VND"],
        ),
    ],
    from_currency: Annotated[
        str,
        Query(
            alias="from",
            description="Source ISO 4217 code (exact, case-insensitive).",
            examples=["USD"],
        ),
    ] = "USD",
    amount: Annotated[
        float,
        Query(gt=0, description="Amount in the source currency.", examples=[100]),
    ] = 1.0,
    country: Annotated[
        str | None,
        Query(
            description=(
                "Optional destination country (fuzzy) — attaches its "
                "`local_currency` so the agent need not know it."
            ),
            examples=["Vietnam"],
        ),
    ] = None,
) -> CurrencyConvertResponse:
    """Convert ``amount`` between currencies via a static mock table; unknown ``country`` is ignored, not an error."""
    return currency.convert(
        from_code=from_currency,
        to_code=to,
        amount=amount,
        country=country or None,
    )
