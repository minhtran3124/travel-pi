"""Visa / entry-requirement tool (wraps ``VisaService`` as an LLM tool).

Read-only lookup over the DB-backed seed visa data (``app/data/visa.py``).
Plain ``@tool`` returning JSON the model relays — no side-panel artifact (cf.
``weather_tools`` which use ``panel_result``). Opens its own session via
``session_scope`` and maps domain errors to ``ToolException`` so the agent can
self-correct. An unknown destination returns ``found: False`` (the service's
documented behaviour, mirrored by ``GET /visa``), never an error.
"""

from __future__ import annotations

from langchain_core.tools import ToolException, tool
from pydantic import Field

from app.exceptions import AppError
from app.schemas.base import AppBaseModel
from app.services.visa_service import VisaService
from app.tools._base import dump, log_tool_call, session_scope, tool_error


class GetVisaArgs(AppBaseModel):
    city: str | None = Field(
        None,
        description=(
            "City to get visa / entry guidance for (fuzzy matched); takes "
            "precedence over `country`. At least one of `city` or `country` "
            "is required."
        ),
    )
    country: str | None = Field(
        None,
        description=(
            "Country to get visa / entry guidance for (fuzzy matched). At "
            "least one of `city` or `country` is required."
        ),
    )


@tool(args_schema=GetVisaArgs)
def get_visa(city: str | None = None, country: str | None = None) -> dict:
    """Get visa / entry-requirement guidance for a destination (city or country).

    Provide at least one of ``city`` or ``country`` (both fuzzy — typo/case
    tolerant). ``city`` takes precedence and resolves its own country. An
    unknown or misspelled destination returns ``found: false`` rather than an
    error — relay the ``disclaimer`` to the traveller unchanged, since it is
    general and nationality-dependent guidance.

    :param city: City to get visa guidance for (fuzzy matched); takes precedence over ``country``.
    :param country: Country to get visa guidance for (fuzzy matched).
    :return: ``{city, country, found, entry, disclaimer}``.
    """
    log_tool_call("get_visa", locals())
    if not (city or None) and not (country or None):
        raise ToolException("Provide either 'city' or 'country'.")

    with session_scope() as s:
        try:
            return dump(
                VisaService(s).get_visa(city=city or None, country=country or None)
            )
        except AppError as e:
            raise tool_error(e) from e


VISA_TOOLS = [get_visa]
