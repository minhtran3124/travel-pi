"""Local-tips tool (wraps ``TipService`` as an LLM tool).

Read-only lookup over the DB-backed seed tips (``app/data/tips.py``). Plain
``@tool`` returning text/JSON the model relays — no side-panel artifact (cf.
``weather_tools`` which use ``panel_result``). Opens its own session via
``session_scope`` and maps domain errors to ``ToolException`` so the agent can
self-correct. An unknown location returns ``count: 0`` (the service's documented
behaviour), never an error.
"""

from __future__ import annotations

from langchain_core.tools import ToolException, tool

from app.exceptions import AppError
from app.services.tip_service import TipService
from app.tools._base import dump, log_tool_call, session_scope


@tool
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
    :param category: Optional filter — transport, money, safety, culture, food,
        connectivity, health, etiquette, best_time, or language.
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
            raise ToolException(str(e)) from e


TIP_TOOLS = [get_local_tips]
