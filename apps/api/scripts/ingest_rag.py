"""Ingest the travel-knowledge corpus into the configured RAG vector store.

Usage: ``python scripts/ingest_rag.py`` (against a Postgres ``DATABASE_URL`` so
embeddings persist; idempotent upsert on stable document ids).
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
