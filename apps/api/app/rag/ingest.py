"""RAG ingestion for visa + local-tips content (specs/travel-knowledge-rag).

Turns DB-backed reference content (visa policies, local tips, country summaries)
into vector-store documents. Records are serialised to a consistent
natural-language template (never raw JSON) before embedding; long prose is
chunked. Reads through the service/repository layer, not ``app.data`` directly,
per the repo's seed-source rule ("``from app.data`` appears only in
``app/db/seed.py``").

Stable document ids (``visa-{country}``, ``summary-{country}``, and a
country+title key for tips) make re-ingesting an upsert rather than an append —
idempotent on every backend.
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
    """Split prose into overlapping chunks (short text passes through as one).

    :param text: The text to split.
    :return: The list of chunks.
    """
    return _splitter.split_text(text)


def _yes_no(flag: bool) -> str:
    """Render a boolean as ``"available"`` / ``"not available"`` for prose.

    :param flag: The boolean to render.
    :return: The human-readable availability string.
    """
    return "available" if flag else "not available"


def visa_to_document(country: str, entry: EntryRequirements) -> Document:
    """Serialise a visa record into an embedding-friendly document.

    :param country: The destination country name.
    :param entry: The entry requirements for that country.
    :return: The embedding-friendly document.
    """
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
    """Serialise a local tip into an embedding-friendly document.

    :param tip: The tip to serialise (carries scope, category, title, content).
    :param country: The country the tip applies to (resolved by the caller).
    :param city: The city the tip applies to, when the scope is ``"city"``;
        ``None`` for country-wide tips.
    :return: The embedding-friendly document.
    """
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
    """Serialise a country overview into an embedding-friendly document.

    :param country: The country name.
    :param summary: The 2–3 sentence natural-language overview.
    :return: The embedding-friendly document.
    """
    return Document(
        page_content=f"{country} — destination overview.\n{summary}",
        metadata={"source": "summary", "country": country},
    )


def build_knowledge_corpus(session: Session) -> list[Document]:
    """Build the full visa + tips + summaries document corpus from the seeded DB.

    Iterates every country that has a visa record (the visa repo's ``countries``),
    every country-wide + city-scoped tip, and every country summary. Reads through
    the repository layer so the corpus reflects the seeded DB, not ``app.data``
    directly. City tips resolve their country from the city record.

    :param session: The DB session used to load the reference content.
    :return: The list of documents to embed.
    """
    visa_repo = VisaRepository(session)
    tip_repo = TipRepository(session)
    city_repo = CityRepository(session)
    country_repo = CountryRepository(session)

    docs: list[Document] = []

    # Visa records.
    for country in visa_repo.countries():
        entry = visa_repo.get(country)
        if entry is not None:
            docs.append(visa_to_document(country, entry))

    # City rows drive both the country set (for country-wide tips) and the
    # city-scoped tips — load them once.
    cities = city_repo.list_with_counts()

    # Country-wide tips.
    for country in sorted({c.country for c in cities}):
        for tip in tip_repo.for_location("country", country):
            docs.append(tip_to_document(tip, country=country, city=None))

    # City-scoped tips (resolve the country from the city record).
    for city in cities:
        for tip in tip_repo.for_location("city", city.name):
            docs.append(tip_to_document(tip, country=city.country, city=city.name))

    # Country summaries (only for countries present on city records, matching
    # ``TipRepository.country_summary``'s resolution target).
    for country in country_repo.distinct_names():
        summary = tip_repo.country_summary(country)
        if summary:
            docs.append(summary_to_document(country, summary))

    return docs


def _doc_id(doc: Document) -> str:
    """Derive a stable upsert id for a corpus document from its metadata.

    :param doc: The document to derive an id for.
    :return: A stable id string unique per (source, country, [city,] category, title).
    """
    src = doc.metadata["source"]
    if src == "visa":
        return f"visa-{doc.metadata['country']}"
    if src == "summary":
        return f"summary-{doc.metadata['country']}"
    # tip — scope it by city when present so a country tip and a same-titled city
    # tip don't collide, and by category so two same-titled tips in one location
    # (the Tip model is unique on scope/key/position, not title) stay distinct;
    # the title keeps it stable across re-ingests.
    country = doc.metadata["country"]
    category = doc.metadata["category"]
    title = doc.metadata["title"]
    if "city" in doc.metadata:
        return f"tip-{doc.metadata['city']}-{country}-{category}-{title}"
    return f"tip-{country}-{category}-{title}"


def ingest_knowledge(store: VectorStore, session: Session) -> int:
    """Embed the visa + tips + summaries corpus into the store (idempotent upsert).

    Long content is split into overlapping chunks (short content passes through as
    one) before embedding, so a detail buried in a long tip embeds against its own
    chunk vector rather than the whole record's averaged vector. Passes stable
    ``ids`` derived from the record keys (chunk-suffixed when a record splits) so
    re-ingesting the same corpus upserts existing entries instead of appending
    duplicates.

    :param store: The vector store to embed into.
    :param session: The DB session used to load the reference content.
    :return: The document (chunk) count ingested.
    """
    docs = build_knowledge_corpus(session)
    if not docs:
        return 0
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
    store.add_documents(chunked, ids=ids)
    return len(chunked)
