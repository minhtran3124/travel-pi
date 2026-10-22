"""Travel-knowledge retrieval tool over the vector store via hybrid search.

An empty result is a signal (``count: 0``), never an error, and a store/embeddings failure degrades
to the same signal rather than raising.
"""

from __future__ import annotations

import logging

from langchain_core.tools import tool
from pydantic import Field

from app.core.text import best_match
from app.data.countries import resolve_country_alias
from app.rag.embeddings import get_vector_store
from app.rag.retriever import hybrid_search
from app.repositories.city import CityRepository
from app.repositories.country import CountryRepository
from app.schemas.base import AppBaseModel
from app.tools._base import log_tool_call, session_scope

logger = logging.getLogger(__name__)


class SearchTravelKnowledgeArgs(AppBaseModel):
    query: str = Field(
        ...,
        description=(
            "Free-text question about visas, entry requirements, or local "
            "practical advice (money, transport, safety, etiquette, etc.)."
        ),
    )
    country: str | None = Field(
        None,
        description=(
            "Optional destination country to filter results by (fuzzy matched, "
            "e.g. 'Vietnam'). Omit to search across all destinations."
        ),
    )
    city: str | None = Field(
        None,
        description=(
            "Optional city to filter results by (fuzzy matched, e.g. 'Hanoi'). "
            "Only city-scoped tips carry a city; visa and summary documents are "
            "country-wide."
        ),
    )
    source: str | None = Field(
        None,
        description=(
            "Optional corpus filter: 'visa' for entry requirements, 'tip' for "
            "local advice, 'summary' for a country overview. Omit to search all."
        ),
    )


def _resolve_location(
    country: str | None, city: str | None
) -> tuple[str | None, str | None]:
    """Fuzzy-resolve ``country``/``city`` to seeded canonical names: the store filters metadata by exact
    equality, so an inexact name would otherwise exclude matches and return a spurious ``count: 0``."""
    if not country and not city:
        return country, city
    with session_scope() as s:
        if country:
            country = (
                resolve_country_alias(country)
                or best_match(
                    country, CountryRepository(s).distinct_names(), [lambda c: c]
                )
                or country
            )
        if city:
            city = (
                best_match(city, CityRepository(s).distinct_names(), [lambda c: c])
                or city
            )
    return country, city


@tool(args_schema=SearchTravelKnowledgeArgs)
def search_travel_knowledge(
    query: str,
    country: str | None = None,
    city: str | None = None,
    source: str | None = None,
) -> dict:
    """Search the travel knowledge base for visa rules and local tips matching a query.

    Use this for free-text questions about **entry requirements** (visa-free days,
    visa-on-arrival, e-visa, passport validity) or **practical local advice**
    (cash, transport, safety, etiquette, connectivity, best time to visit) — it
    ranks the seeded knowledge passages by a mix of meaning and keywords, so a
    phrasing like "do I need a visa for a 45-day stay in Vietnam?" still finds the
    right passage even without naming a category. Pass ``country``/``city`` to
    narrow to one destination (fuzzy matched), or ``source`` to one corpus
    (``visa``/``tip``/``summary``).

    Results are guidance snippets, not live rules — always remind the traveller
    that visa requirements depend on nationality and change, and to confirm with
    the official immigration authority.

    :param query: Free-text question about visas or local advice.
    :param country: Optional destination country to filter by (fuzzy matched).
    :param city: Optional city to filter by (city-scoped tips only, fuzzy matched).
    :param source: Optional corpus filter: ``visa`` / ``tip`` / ``summary``.
    :return: ``{results: [{content, metadata}], count}`` — ``count: 0`` when
        nothing matched (a signal, not an error).
    """
    log_tool_call("search_travel_knowledge", locals())
    try:
        country, city = _resolve_location(country, city)
        filters: dict[str, str] = {}
        if country:
            filters["country"] = country
        if city:
            filters["city"] = city
        if source:
            filters["source"] = source
        store = get_vector_store()
        docs = hybrid_search(store, query, filters=filters or None, k=5)
    except Exception:
        logger.exception(
            "[search_travel_knowledge] retrieval failed; returning empty result"
        )
        return {"results": [], "count": 0}
    logger.info(
        "[tool] search_travel_knowledge -> %d result(s) (filters=%s)",
        len(docs),
        filters or None,
    )
    results = [{"content": d.page_content, "metadata": d.metadata} for d in docs]
    return {"results": results, "count": len(results)}


KNOWLEDGE_TOOLS = [search_travel_knowledge]
