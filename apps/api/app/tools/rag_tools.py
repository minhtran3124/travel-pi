"""Travel-knowledge retrieval tool (specs/travel-knowledge-rag).

Lets the concierge pull visa / entry-requirement and local-tips knowledge from the
vector store via hybrid (semantic + lexical, RRF) search. Backed by pgvector in
production; against the in-memory store (SQLite/tests) it returns documents once
the corpus has been auto-ingested at startup (see ``core/lifespan``).

Follows the same conventions as the other service-wrapping tools: a hand-authored
``AppBaseModel`` args schema, ``log_tool_call`` first, and a plain dict return
(``{results, count}``) that is always JSON-able. An empty result is a signal
(``count: 0``), never an error — the concierge answers from its other tools when
retrieval is empty.
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import Field

from app.rag.embeddings import get_vector_store
from app.rag.retriever import hybrid_search
from app.schemas.base import AppBaseModel
from app.tools._base import log_tool_call


class SearchTravelKnowledgeArgs(AppBaseModel):
    """Args for ``search_travel_knowledge`` (hand-authored schema)."""

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
            "Optional destination country to filter results by (exact seeded "
            "name, e.g. 'Vietnam'). Omit to search across all destinations."
        ),
    )
    city: str | None = Field(
        None,
        description=(
            "Optional city to filter results by (exact seeded name, e.g. "
            "'Hanoi'). Only city-scoped tips carry a city; visa and summary "
            "documents are country-wide."
        ),
    )
    source: str | None = Field(
        None,
        description=(
            "Optional corpus filter: 'visa' for entry requirements, 'tip' for "
            "local advice, 'summary' for a country overview. Omit to search all."
        ),
    )


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
    narrow to one destination, or ``source`` to one corpus (``visa``/``tip``/
    ``summary``).

    Results are guidance snippets, not live rules — always remind the traveller
    that visa requirements depend on nationality and change, and to confirm with
    the official immigration authority.

    :param query: Free-text question about visas or local advice.
    :param country: Optional destination country to filter by.
    :param city: Optional city to filter by (city-scoped tips only).
    :param source: Optional corpus filter: ``visa`` / ``tip`` / ``summary``.
    :return: ``{results: [{content, metadata}], count}`` — ``count: 0`` when
        nothing matched (a signal, not an error).
    """
    log_tool_call("search_travel_knowledge", locals())
    store = get_vector_store()
    filters: dict[str, str] = {}
    if country:
        filters["country"] = country
    if city:
        filters["city"] = city
    if source:
        filters["source"] = source
    docs = hybrid_search(store, query, filters=filters or None, k=5)
    results = [{"content": d.page_content, "metadata": d.metadata} for d in docs]
    return {"results": results, "count": len(results)}


KNOWLEDGE_TOOLS = [search_travel_knowledge]
