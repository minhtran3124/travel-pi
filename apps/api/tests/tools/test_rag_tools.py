"""Tests for search_travel_knowledge (specs/travel-knowledge-rag)."""

from langchain_core.embeddings import DeterministicFakeEmbedding


def test_search_travel_knowledge_has_hand_authored_args_schema():
    from app.tools.rag_tools import SearchTravelKnowledgeArgs, search_travel_knowledge

    assert search_travel_knowledge.args_schema is SearchTravelKnowledgeArgs
    assert search_travel_knowledge.args_schema.__module__.startswith("app.tools")


def test_search_travel_knowledge_schema_required_optional():
    from app.tools.rag_tools import search_travel_knowledge

    schema = search_travel_knowledge.get_input_schema().model_json_schema()
    assert schema["required"] == ["query"]
    for opt in ("country", "city", "source"):
        assert opt in schema["properties"]
        assert opt not in schema.get("required", [])


def _fake_embeddings(monkeypatch):
    """Force the deterministic fake embeddings so the tool never hits OpenAI.

    ``get_embeddings`` reads ``settings.openai_api_key``; a real key in
    ``apps/api/.env`` would otherwise make the tool call OpenAI. Patch the
    function directly so the key (and ``agent_db``'s settings rebuild) can't win.
    """
    import app.core.embeddings as ce
    from app.rag import embeddings as rag_emb

    fake = DeterministicFakeEmbedding(size=1536)
    monkeypatch.setattr(ce, "get_embeddings", lambda: fake)
    monkeypatch.setattr(rag_emb, "get_embeddings", lambda: fake)
    return fake


def _ingest_corpus(agent_db):
    """Embed the seeded visa/tips corpus into the (cached) store the tool uses.

    The tool resolves a cached singleton store; in a unit test it starts empty
    (no lifespan pre-warm), so ingest once before querying.
    """
    from app.db.engine import get_session_factory
    from app.rag.embeddings import get_vector_store
    from app.rag.ingest import ingest_knowledge

    store = get_vector_store(database_url=agent_db)
    with get_session_factory(agent_db)() as session:
        ingest_knowledge(store, session)


def test_search_travel_knowledge_returns_results_on_seeded_db(
    agent_db, reset_store, monkeypatch
):
    _fake_embeddings(monkeypatch)
    _ingest_corpus(agent_db)
    from app.tools.rag_tools import search_travel_knowledge

    out = search_travel_knowledge.invoke(
        {"query": "do I need a visa for Vietnam", "source": "visa"}
    )
    assert isinstance(out, dict)
    assert out["count"] >= 1
    assert isinstance(out["results"], list)
    assert all("content" in r and "metadata" in r for r in out["results"])
    assert all(r["metadata"]["source"] == "visa" for r in out["results"])


def test_search_travel_knowledge_country_filter(agent_db, reset_store, monkeypatch):
    _fake_embeddings(monkeypatch)
    _ingest_corpus(agent_db)
    from app.tools.rag_tools import search_travel_knowledge

    out = search_travel_knowledge.invoke(
        {"query": "transport and money tips", "country": "Vietnam"}
    )
    assert out["count"] >= 1
    assert all(r["metadata"]["country"] == "Vietnam" for r in out["results"])


def test_search_travel_knowledge_country_filter_fuzzy(
    agent_db, reset_store, monkeypatch
):
    """Free-text country resolves to the seeded name before the exact filter."""
    _fake_embeddings(monkeypatch)
    _ingest_corpus(agent_db)
    from app.tools.rag_tools import search_travel_knowledge

    # Lowercase 'vietnam' would miss an exact metadata match; fuzzy resolution
    # maps it to the seeded 'Vietnam' so the filter still surfaces its tips.
    out = search_travel_knowledge.invoke(
        {"query": "transport and money tips", "country": "vietnam"}
    )
    assert out["count"] >= 1
    assert all(r["metadata"]["country"] == "Vietnam" for r in out["results"])


def test_search_travel_knowledge_degrades_to_empty_on_store_failure(monkeypatch):
    """A store/embeddings failure returns the count:0 signal, never raises."""
    import app.tools.rag_tools as rt

    def boom():
        raise RuntimeError("vector store unavailable")

    monkeypatch.setattr(rt, "get_vector_store", boom)
    out = rt.search_travel_knowledge.invoke({"query": "do I need a visa for Vietnam"})
    assert out == {"results": [], "count": 0}


def test_search_travel_knowledge_empty_when_no_match(
    agent_db, reset_store, monkeypatch
):
    _fake_embeddings(monkeypatch)
    _ingest_corpus(agent_db)
    from app.tools.rag_tools import search_travel_knowledge

    # A filter matching no documents yields the empty signal — the filter is
    # pushed into similarity_search, so an unknown country returns nothing
    # (an unfiltered nonsense query still returns nearest neighbours).
    out = search_travel_knowledge.invoke(
        {"query": "visa requirements", "country": "Atlantis"}
    )
    assert out["count"] == 0
    assert out["results"] == []


def test_search_travel_knowledge_registered_readonly_on_concierge():
    from app.tools.registry import TOOL_METADATA, get_tools_for

    assert "search_travel_knowledge" in {t.name for t in get_tools_for("concierge")}
    assert TOOL_METADATA["search_travel_knowledge"] == {
        "readOnly": True,
        "destructive": False,
    }


def test_search_travel_knowledge_not_in_other_domains():
    from app.tools.registry import get_tools_for

    for domain in ("planner", "journal", "booking", "budget"):
        assert "search_travel_knowledge" not in {t.name for t in get_tools_for(domain)}
