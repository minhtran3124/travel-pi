"""Local-tips schemas: practical destination advice for the Travel Planner agent."""

from pydantic import Field

from app.schemas.base import AppBaseModel


class Tip(AppBaseModel):
    """A single piece of practical local advice."""

    id: str = Field(description="Stable positional ID — do not parse for meaning.")
    category: str = Field(
        description=(
            "Tip category: 'transport', 'money', 'safety', 'culture', "
            "'food', 'connectivity', 'health', 'etiquette', 'best_time', "
            "'language', etc."
        ),
        examples=["transport"],
    )
    scope: str = Field(
        description=(
            "'country' if the tip applies to the whole country, 'city' if "
            "it is city-specific."
        ),
        examples=["country"],
    )
    title: str = Field(description="Short headline.", examples=["Use Grab for short rides"])
    content: str = Field(description="Full advice text.")
    is_essential: bool = Field(
        default=False,
        description="True for must-know advice — set `essential_only=true` on GET /tips to keep only these.",
    )
    location: str | None = Field(
        default=None,
        description=(
            "Where the tip applies (city or country name). Only populated "
            "when a response mixes destinations (e.g. the dashboard view)."
        ),
    )


class TipsResponse(AppBaseModel):
    """Response body for ``GET /tips`` — country tips merged with city tips."""

    city: str | None = Field(
        default=None, description="City that was queried, if any.", examples=["Da Nang"]
    )
    country: str = Field(description="Country resolved from the query.", examples=["Vietnam"])
    count: int = Field(description="Number of tips returned.")
    summary: str = Field(description="One-line headline describing the result set.")
    tips: list[Tip]
