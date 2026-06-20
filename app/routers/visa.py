"""Visa / entry-requirement endpoint — static, general guidance."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.error import error_responses
from app.schemas.visa import VisaResponse
from app.services.visa_service import VisaService, get_visa_service

router = APIRouter(prefix="/visa", tags=["visa"])

VisaDep = Annotated[VisaService, Depends(get_visa_service)]


@router.get(
    "",
    response_model=VisaResponse,
    summary="Get visa / entry guidance for a city or country",
    responses=error_responses(422),
)
def get_visa(
    visa: VisaDep,
    city: Annotated[
        str | None,
        Query(
            description="City name (fuzzy — typo/case tolerant) — resolves its own country.",
            examples=["Da Nang"],
        ),
    ] = None,
    country: Annotated[
        str | None,
        Query(
            description="Country name (fuzzy — typo/case tolerant).",
            examples=["Vietnam"],
        ),
    ] = None,
) -> VisaResponse:
    """Return general visa / entry guidance for a destination.

    Provide either ``city`` or ``country``. Unknown locations return
    ``found: false`` (not a 404). Guidance is general and nationality-dependent
    — see the ``disclaimer`` field.
    """
    # Coerce empty strings → None (HTML forms send "" for an unset field).
    city = city or None
    country = country or None

    if not city and not country:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either 'city' or 'country'.",
        )

    return visa.get_visa(city=city, country=country)
