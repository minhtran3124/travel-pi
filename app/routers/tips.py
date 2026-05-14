"""Local tips endpoint: curated, practical destination advice."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.tip import TipsResponse
from app.services import tip_service

router = APIRouter(prefix="/tips", tags=["tips"])


@router.get(
    "",
    response_model=TipsResponse,
    summary="Get local tips for a city or country",
)
def get_tips(
    city: Annotated[
        str | None,
        Query(description="City name — resolves its own country", examples=["Hanoi"]),
    ] = None,
    country: Annotated[
        str | None,
        Query(description="Country name, case-insensitive", examples=["Vietnam"]),
    ] = None,
    category: Annotated[
        str | None,
        Query(
            description=(
                "Filter by category: transport | money | safety | culture | food | "
                "connectivity | health | etiquette | best_time | language"
            ),
            examples=["money"],
        ),
    ] = None,
    essential_only: Annotated[
        bool,
        Query(description="Return only the must-know (essential) tips"),
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
    if category and category.strip().lower() not in tip_service.VALID_CATEGORIES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid category '{category}'. "
            f"Valid: {sorted(tip_service.VALID_CATEGORIES)}",
        )

    return tip_service.get_tips(
        city=city,
        country=country,
        category=category,
        essential_only=essential_only,
    )
