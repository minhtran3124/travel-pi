"""RAG ingestion (specs/travel-agent Task 4.2).

Turns DB-backed reference content (places, tips) into vector-store documents.
Records are serialised to a consistent template string (never raw JSON) before
embedding; long prose is chunked. Reads through the service/repository layer, not
``app.data`` directly, per the repo's seed-source rule.
"""

from __future__ import annotations

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy.orm import Session

from app.services.place_service import PlaceService

_splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=50)


def chunk_text(text: str) -> list[str]:
    """Split prose into overlapping chunks (short text passes through as one).

    :param text: The text to split.
    :return: The list of chunks.
    """
    return _splitter.split_text(text)


def place_to_document(place) -> Document:
    """Serialise a place into a single embedding-friendly document.

    :param place: The place to serialise.
    :return: The embedding-friendly document.
    """
    parts = [f"{place.name} — {place.category} in {place.city}, {place.country}."]
    description = getattr(place, "description", None)
    if description:
        parts.append(description)
    return Document(
        page_content=" ".join(parts),
        metadata={
            "id": place.id,
            "city": place.city,
            "country": place.country,
            "category": place.category,
            "source": "place",
        },
    )


def ingest_places(store: VectorStore, session: Session) -> int:
    """Embed every catalog place into the store.

    Passes stable ``ids`` derived from ``place.id`` so that re-ingesting the
    same catalog upserts existing entries instead of appending duplicates.

    :param store: The vector store to embed into.
    :param session: The DB session used to load the catalog.
    :return: The document count.
    """
    places = PlaceService(session).list_places()
    docs = [place_to_document(p) for p in places]
    if docs:
        ids = [f"place-{p.id}" for p in places]
        store.add_documents(docs, ids=ids)
    return len(docs)
