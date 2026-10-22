"""Visa / entry-requirement schemas for ``GET /visa`` — general guidance only; real rules are nationality-dependent."""

from pydantic import Field

from app.schemas.base import AppBaseModel


class EntryRequirements(AppBaseModel):
    """Typical entry requirements for a destination country."""

    visa_free_days: int = Field(
        description="Typical visa-free stay in days for many nationalities; 0 if a visa is generally required.",
        examples=[45],
    )
    visa_on_arrival: bool = Field(
        description="Whether a visa-on-arrival is commonly available.",
        examples=[True],
    )
    e_visa: bool = Field(
        description="Whether an online / e-visa option exists.", examples=[True]
    )
    passport_validity_months: int = Field(
        description="Months of passport validity typically required beyond entry; 0 means 'valid for the duration of stay'.",
        examples=[6],
    )
    summary: str = Field(
        description="One natural-language sentence the agent can quote.",
        examples=[
            "Many nationalities get 45 days visa-free; others can apply for a 90-day e-visa online before arrival."
        ],
    )


class VisaResponse(AppBaseModel):
    """Response body for ``GET /visa``."""

    city: str | None = Field(
        default=None,
        description="City that was queried, if any (resolved name).",
        examples=["Da Nang"],
    )
    country: str = Field(
        description="Country resolved from the query.", examples=["Vietnam"]
    )
    found: bool = Field(
        description="True if entry info was found for the resolved country.",
        examples=[True],
    )
    entry: EntryRequirements | None = Field(
        default=None,
        description="Entry requirements for the resolved country; null when the location was not recognised.",
    )
    disclaimer: str = Field(
        description="Mandatory caveat — guidance is general and nationality-dependent."
    )
