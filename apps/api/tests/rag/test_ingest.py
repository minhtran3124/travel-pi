"""Corpus rendering for visa + local tips (specs/travel-knowledge-rag, Part 1)."""

from app.rag.ingest import (
    build_knowledge_corpus,
    summary_to_document,
    tip_to_document,
    visa_to_document,
)
from app.schemas.tip import Tip
from app.schemas.visa import EntryRequirements
from langchain_core.documents import Document


def _visa(country: str = "Vietnam", **kw) -> EntryRequirements:
    base: dict = {
        "visa_free_days": 45,
        "visa_on_arrival": True,
        "e_visa": True,
        "passport_validity_months": 6,
        "summary": f"Visa summary for {country}.",
    }
    base.update(kw)
    return EntryRequirements(**base)


def _tip(category: str = "transport", scope: str = "country") -> Tip:
    return Tip(
        id=f"tip_{scope}_xx_01",
        scope=scope,
        category=category,
        title="A sample tip",
        content="Some practical advice text.",
        is_essential=True,
    )


def test_visa_to_document_shape():
    doc = visa_to_document("Vietnam", _visa())
    assert isinstance(doc, Document)
    assert doc.metadata == {"source": "visa", "country": "Vietnam"}
    # Prose includes the country, summary, and the structured facts.
    assert "Vietnam" in doc.page_content
    assert "Visa summary for Vietnam." in doc.page_content
    assert "45 days" in doc.page_content


def test_visa_to_document_visa_required_when_zero_days():
    doc = visa_to_document("Cambodia", _visa(visa_free_days=0))
    assert "generally required" in doc.page_content
    assert (
        "0 days" not in doc.page_content
    )  # the zero is rendered as prose, not "0 days"


def test_visa_to_document_passport_validity_zero_means_duration_of_stay():
    doc = visa_to_document("Japan", _visa(passport_validity_months=0))
    assert "duration of stay" in doc.page_content


def test_tip_to_document_country_scope():
    doc = tip_to_document(_tip(), country="Vietnam", city=None)
    assert doc.metadata["source"] == "tip"
    assert doc.metadata["scope"] == "country"
    assert doc.metadata["country"] == "Vietnam"
    assert "city" not in doc.metadata
    assert "Vietnam" in doc.page_content
    assert "A sample tip" in doc.page_content


def test_tip_to_document_city_scope_carries_city():
    doc = tip_to_document(_tip(scope="city"), country="Vietnam", city="Hanoi")
    assert doc.metadata["scope"] == "city"
    assert doc.metadata["city"] == "Hanoi"
    assert "Hanoi, Vietnam" in doc.page_content


def test_summary_to_document_shape():
    doc = summary_to_document("Vietnam", "Vietnam is diverse and affordable.")
    assert doc.metadata == {"source": "summary", "country": "Vietnam"}
    assert "destination overview" in doc.page_content
    assert "Vietnam is diverse and affordable." in doc.page_content


def test_ingest_knowledge_chunks_long_content(
    reset_store, fake_embeddings, monkeypatch
):
    """Long records are split before embedding (regression: chunk_text was unused)."""
    from app.rag import ingest as ingest_mod
    from app.rag.embeddings import get_vector_store

    long_doc = Document(
        page_content="word " * 500,
        metadata={
            "source": "tip",
            "scope": "country",
            "country": "Vietnam",
            "category": "transport",
            "title": "Long tip",
        },
    )
    monkeypatch.setattr(
        ingest_mod, "build_knowledge_corpus", lambda session: [long_doc]
    )
    store = get_vector_store(database_url="sqlite:///:memory:")
    count = ingest_mod.ingest_knowledge(store, session=None)
    assert count > 1  # the single long tip was chunked into several documents


def test_doc_id_distinguishes_same_title_tips_by_category():
    """Two same-title country tips get distinct ids (regression: id collision)."""
    from app.rag.ingest import _doc_id

    meta = {"source": "tip", "country": "Vietnam", "title": "Getting around"}
    a = Document(page_content="a", metadata={**meta, "category": "transport"})
    b = Document(page_content="b", metadata={**meta, "category": "safety"})
    assert _doc_id(a) != _doc_id(b)


def test_build_knowledge_corpus_covers_all_sources(seeded_session):
    docs = build_knowledge_corpus(seeded_session)
    sources = {d.metadata["source"] for d in docs}
    assert sources == {"visa", "tip", "summary"}
    # Every country with a visa record produces a visa doc.
    from app.repositories.visa import VisaRepository

    visa_countries = set(VisaRepository(seeded_session).countries())
    doc_visa_countries = {
        d.metadata["country"] for d in docs if d.metadata["source"] == "visa"
    }
    assert doc_visa_countries == visa_countries
    # City-scoped tips carry the city in metadata.
    city_tips = [
        d
        for d in docs
        if d.metadata["source"] == "tip" and d.metadata["scope"] == "city"
    ]
    assert city_tips, "expected at least one city-scoped tip in the seed corpus"
    assert all("city" in d.metadata for d in city_tips)
