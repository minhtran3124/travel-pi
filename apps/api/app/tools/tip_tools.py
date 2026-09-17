"""Local-tips tool wrapping ``TipService`` (an unknown location returns ``count: 0``, never an error)."""

from __future__ import annotations

from langchain_core.tools import ToolException, tool
from pydantic import Field

from app.enums import TipCategory
from app.exceptions import AppError
from app.schemas.base import AppBaseModel
from app.services.tip_service import TipService
from app.tools._base import dump, log_tool_call, session_scope, tool_error


class GetLocalTipsArgs(AppBaseModel):
    city: str | None = Field(
        None,
        description=(
            "City to get tips for (fuzzy matched); takes precedence over "
            "`country`. At least one of `city` or `country` is required."
        ),
    )
    country: str | None = Field(
        None,
        description=(
            "Country to get tips for (fuzzy matched). At least one of "
            "`city` or `country` is required."
        ),
    )
    category: TipCategory | None = Field(
        None, description="Optional filter to a single tip category."
    )
    essential_only: bool = Field(
        False, description="Keep only the must-know advice (default False)."
    )


@tool(args_schema=GetLocalTipsArgs)
def get_local_tips(
    city: str | None = None,
    country: str | None = None,
    category: str | None = None,
    essential_only: bool = False,
) -> dict:
    """Get practical local travel tips for a destination (city or country).

    Provide at least one of ``city`` or ``country`` (both fuzzy — typo/case
    tolerant). ``city`` takes precedence and resolves its own country; the
    country-level tips are merged with the city-specific ones. An unknown or
    misspelled location returns ``count: 0`` rather than an error.

    :param city: City to get tips for (fuzzy matched); takes precedence over ``country``.
    :param country: Country to get tips for (fuzzy matched).
    :param category: Optional filter to a single tip category.
    :param essential_only: Keep only the must-know advice (default False).
    :return: ``{city, country, count, summary, tips: [{category, title, content,
        is_essential, ...}]}``.
    """
    log_tool_call("get_local_tips", locals())
    if not (city or None) and not (country or None):
        raise ToolException("Provide either 'city' or 'country'.")

    with session_scope() as s:
        try:
            return dump(
                TipService(s).get_tips(
                    city=city or None,
                    country=country or None,
                    category=category,
                    essential_only=essential_only,
                )
            )
        except AppError as e:
            raise tool_error(e) from e


TIP_TOOLS = [get_local_tips]
