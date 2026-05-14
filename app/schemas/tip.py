"""Local-tips schemas: practical destination advice for the Travel Planner agent."""

from app.schemas.base import AppBaseModel


class Tip(AppBaseModel):
    """A single piece of practical local advice."""

    id: str
    category: str  # transport | money | safety | culture | food | ...
    scope: str  # "country" | "city"
    title: str
    content: str
    is_essential: bool = False


class TipsResponse(AppBaseModel):
    """Response body for ``GET /tips`` — country tips merged with city tips."""

    city: str | None = None
    country: str
    count: int
    summary: str
    tips: list[Tip]
