"""RAG retrieval tool (specs/travel-agent Task 5.2).

Lets the concierge pull destination/POI knowledge from the vector store via
hybrid search. Backed by pgvector in production; against the in-memory store
(SQLite/tests) it returns nothing unless documents were ingested in-process, so
RAG is effectively a Postgres capability — the concierge still answers from its
other tools when retrieval is empty.
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import Field

from app.rag.embeddings import get_vector_store
from app.rag.retriever import hybrid_search
from app.schemas.base import AppBaseModel
from app.tools._base import log_tool_call


class SearchDestinationKnowledgeArgs(AppBaseModel):
    query: str = Field(..., description="Free-text search query.")
    city: str | None = Field(None, description="Optional city to filter results by.")


@tool(args_schema=SearchDestinationKnowledgeArgs)
def search_destination_knowledge(query: str, city: str | None = None) -> list:
    """Search the destination knowledge base for places/notes matching a query.

    :param query: Free-text search query.
    :param city: Optional city to filter results by.
    :return: Matching snippets with their metadata.
    """
    log_tool_call("search_destination_knowledge", locals())
    store = get_vector_store()
    filters = {"city": city} if city else None
    docs = hybrid_search(store, query, filters=filters, k=5)
    return [{"content": d.page_content, "metadata": d.metadata} for d in docs]


RAG_TOOLS = [search_destination_knowledge]
