"""Ingest the travel-knowledge corpus into the RAG vector store (specs/travel-knowledge-rag).

Usage: ``python scripts/ingest_rag.py``

Builds the configured vector store (pgvector on Postgres, in-memory otherwise) and
embeds the visa + local-tips + country-summary corpus, reading through the
repository layer from the seeded DB. Intended to be run against a Postgres
``DATABASE_URL`` where the embeddings persist; on SQLite it populates an
in-memory store (useful for a one-off local check, but not persisted). Re-running
is an idempotent upsert (stable document ids).
"""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.db.engine import get_session_factory
from app.rag.embeddings import get_vector_store
from app.rag.ingest import ingest_knowledge

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ingest_rag")


def main() -> None:
    """Ingest the travel-knowledge corpus into the configured vector store.

    :return: None.
    """
    settings = get_settings()
    store = get_vector_store()
    with get_session_factory(settings.database_url)() as session:
        count = ingest_knowledge(store, session)
    logger.info(
        "Ingested %d travel-knowledge documents into %s",
        count,
        type(store).__name__,
    )


if __name__ == "__main__":
    main()
