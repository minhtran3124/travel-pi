"""Local tips endpoint: curated, practical destination advice."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.enums import TipCategory
from app.schemas.error import error_responses
from app.schemas.tip import TipsResponse
from app.services import tip_service

router = APIRouter(prefix="/tips", tags=["tips"])


@router.get(
    "",
    response_model=TipsResponse,
    summary="Get local tips for a city or country",
    responses=error_responses(422),
)
def get_tips(
    city: Annotated[
        str | None,
        Query(
            description=(
                "City name (fuzzy — typo/case tolerant) — resolves its own country"
            ),
            example="Hanoi",
        ),
    ] = None,
    country: Annotated[
        str | None,
        Query(
            description="Country name (fuzzy — typo/case tolerant)",
            example="Vietnam",
        ),
    ] = None,
    category: Annotated[
        TipCategory | None,
        Query(
            description="Filter by category — Swagger renders the dropdown.",
            example="money",
        ),
    ] = None,
    essential_only: Annotated[
        bool,
        Query(
            description="Return only the must-know (essential) tips",
            example=True,
        ),
    ] = False,
) -> TipsResponse:
    """Return country-level tips merged with any city-specific tips.

    Provide either ``city`` or ``country``. Unknown locations return
    ``count: 0`` (not a 404). Empty-string params are treated as missing so
    HTML forms don't need to strip blanks.
    """
    # Coerce empty strings → None (HTML forms send "" for an unset field).
    city = city or None
    country = country or None

    if not city and not country:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either 'city' or 'country'.",
        )

    return tip_service.get_tips(
        city=city,
        country=country,
        category=category.value if category else None,
        essential_only=essential_only,
    )
