"""Ingest reference content into the RAG vector store (specs/travel-agent).

Usage: python scripts/ingest_rag.py

Builds the configured vector store (pgvector on Postgres, in-memory otherwise)
and embeds all catalog places. Intended to be run after seeding, against a
Postgres DATABASE_URL where the embeddings persist.
"""

from __future__ import annotations

import logging

from app.core.config import get_settings
from app.db.engine import get_session_factory
from app.rag.embeddings import get_vector_store
from app.rag.ingest import ingest_places

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ingest_rag")


def main() -> None:
    settings = get_settings()
    store = get_vector_store()
    with get_session_factory(settings.database_url)() as session:
        count = ingest_places(store, session)
    logger.info("Ingested %d place documents into the vector store", count)


if __name__ == "__main__":
    main()
