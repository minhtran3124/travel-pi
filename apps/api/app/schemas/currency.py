"""Currency-conversion schemas for ``GET /currency/convert`` (mock FX; ``from``/``to`` are reserved-word aliases)."""

from pydantic import ConfigDict, Field

from app.schemas.base import AppBaseModel


class LocalCurrency(AppBaseModel):
    """The destination country's own currency, when a ``country`` is supplied."""

    code: str = Field(description="ISO 4217 code.", examples=["VND"])
    name: str = Field(description="Currency full name.", examples=["Vietnamese Dong"])


class CurrencyConvertResponse(AppBaseModel):
    """Response body for ``GET /currency/convert``."""

    # Construct by field name while serialising under the ``from``/``to`` aliases.
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    from_currency: str = Field(
        alias="from", description="Source ISO 4217 code.", examples=["USD"]
    )
    to_currency: str = Field(
        alias="to", description="Target ISO 4217 code.", examples=["VND"]
    )
    rate: float = Field(
        description="Units of the target currency per 1 unit of the source.",
        examples=[25400.0],
    )
    amount: float = Field(
        description="Source amount that was converted.", examples=[100.0]
    )
    converted: float = Field(
        description="Converted amount, rounded to 2 decimals.", examples=[2540000.0]
    )
    last_updated: str = Field(
        description="Date of the mock rate snapshot (this is not live FX data).",
        examples=["2026-06-01"],
    )
    local_currency: LocalCurrency | None = Field(
        default=None,
        description=(
            "The local currency of the `country` query param, if one was given "
            "and resolved — so an agent need not know it. Null otherwise."
        ),
    )
