"""RAG ingestion turning DB-backed reference content into vector-store documents.

Records are serialised to a natural-language template (never raw JSON) before embedding. Stable
document ids make re-ingesting an idempotent upsert rather than an append.
"""

from __future__ import annotations

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy.orm import Session

from app.repositories.city import CityRepository
from app.repositories.country import CountryRepository
from app.repositories.tip import TipRepository
from app.repositories.visa import VisaRepository
from app.schemas.tip import Tip as TipSchema
from app.schemas.visa import EntryRequirements

_splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=50)


def chunk_text(text: str) -> list[str]:
    """Split prose into overlapping chunks (short text passes through as one)."""
    return _splitter.split_text(text)


def _yes_no(flag: bool) -> str:
    """Render a boolean as ``"available"`` / ``"not available"`` for prose."""
    return "available" if flag else "not available"


def visa_to_document(country: str, entry: EntryRequirements) -> Document:
    """Serialise a visa record into an embedding-friendly document."""
    validity = (
        f"{entry.passport_validity_months} months beyond entry"
        if entry.passport_validity_months
        else "valid for the duration of stay"
    )
    visa_free = (
        f"Visa-free stay: {entry.visa_free_days} days."
        if entry.visa_free_days
        else "A visa is generally required (no visa-free stay)."
    )
    content = (
        f"Visa & entry requirements for {country}.\n"
        f"{entry.summary}\n"
        f"{visa_free} "
        f"Visa-on-arrival: {_yes_no(entry.visa_on_arrival)}. "
        f"E-visa: {_yes_no(entry.e_visa)}. "
        f"Passport validity: {validity}."
    )
    return Document(
        page_content=content,
        metadata={"source": "visa", "country": country},
    )


def tip_to_document(tip: TipSchema, *, country: str, city: str | None) -> Document:
    """Serialise a local tip into an embedding-friendly document."""
    place = f"{city}, {country}" if city else country
    essential = ", essential" if tip.is_essential else ""
    content = (
        f"Local tip — {place} ({tip.category}{essential}): {tip.title}.\n{tip.content}"
    )
    metadata: dict = {
        "source": "tip",
        "scope": tip.scope,
        "country": country,
        "category": tip.category,
        "title": tip.title,
        "is_essential": tip.is_essential,
    }
    if city:
        metadata["city"] = city
    return Document(page_content=content, metadata=metadata)


def summary_to_document(country: str, summary: str) -> Document:
    """Serialise a country overview into an embedding-friendly document."""
    return Document(
        page_content=f"{country} — destination overview.\n{summary}",
        metadata={"source": "summary", "country": country},
    )


def build_knowledge_corpus(session: Session) -> list[Document]:
    """Build the full visa + tips + summaries document corpus from the seeded DB via the repository
    layer, so the corpus reflects the seeded DB rather than ``app.data`` directly."""
    visa_repo = VisaRepository(session)
    tip_repo = TipRepository(session)
    city_repo = CityRepository(session)
    country_repo = CountryRepository(session)

    docs: list[Document] = []

    for country in visa_repo.countries():
        entry = visa_repo.get(country)
        if entry is not None:
            docs.append(visa_to_document(country, entry))

    # City rows drive both the country set and the city-scoped tips — load them once.
    cities = city_repo.list_with_counts()

    for country in sorted({c.country for c in cities}):
        for tip in tip_repo.for_location("country", country):
            docs.append(tip_to_document(tip, country=country, city=None))

    # City-scoped tips resolve the country from the city record.
    for city in cities:
        for tip in tip_repo.for_location("city", city.name):
            docs.append(tip_to_document(tip, country=city.country, city=city.name))

    for country in country_repo.distinct_names():
        summary = tip_repo.country_summary(country)
        if summary:
            docs.append(summary_to_document(country, summary))

    return docs


def _doc_id(doc: Document) -> str:
    """Derive a stable upsert id for a corpus document from its metadata."""
    src = doc.metadata["source"]
    if src == "visa":
        return f"visa-{doc.metadata['country']}"
    if src == "summary":
        return f"summary-{doc.metadata['country']}"
    # Scope tip ids by city and category so same-titled tips in one location don't collide.
    country = doc.metadata["country"]
    category = doc.metadata["category"]
    title = doc.metadata["title"]
    if "city" in doc.metadata:
        return f"tip-{doc.metadata['city']}-{country}-{category}-{title}"
    return f"tip-{country}-{category}-{title}"


def _chunk_corpus(docs: list[Document]) -> tuple[list[Document], list[str]]:
    """Split each corpus document into embed-ready chunks with stable, upsert-safe ids."""
    chunked: list[Document] = []
    ids: list[str] = []
    for doc in docs:
        base = _doc_id(doc)
        chunks = chunk_text(doc.page_content)
        if len(chunks) == 1:
            chunked.append(doc)
            ids.append(base)
            continue
        for i, chunk in enumerate(chunks):
            chunked.append(Document(page_content=chunk, metadata={**doc.metadata}))
            ids.append(f"{base}#{i}")
    return chunked, ids


def corpus_document_ids(session: Session) -> list[str]:
    """Return the stable ids ``ingest_knowledge`` would upsert for the current corpus — cheap enough
    to call at startup to check whether a persisted store is already up to date (see ``lifespan``),
    without embedding anything."""
    _, ids = _chunk_corpus(build_knowledge_corpus(session))
    return ids


def ingest_knowledge(store: VectorStore, session: Session) -> int:
    """Embed the corpus into the store as an idempotent upsert. Long content is chunked so a detail
    buried in a long tip embeds against its own vector, and stable chunk-suffixed ids let a re-ingest
    upsert rather than append duplicates."""
    docs = build_knowledge_corpus(session)
    if not docs:
        return 0
    chunked, ids = _chunk_corpus(docs)
    store.add_documents(chunked, ids=ids)
    return len(chunked)
