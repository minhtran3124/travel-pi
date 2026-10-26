"""Shared embeddings helper (relocated from tests/rag/test_embeddings.py;
specs/remove-rag-feature)."""

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

pytestmark = pytest.mark.usefixtures("isolated_settings_env")


def test_get_embeddings_fake_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    from app.core.embeddings import get_embeddings

    emb = get_embeddings()
    assert isinstance(emb, DeterministicFakeEmbedding)
    # deterministic: same text -> same vector
    assert emb.embed_query("Tokyo") == emb.embed_query("Tokyo")
    get_settings.cache_clear()


def _warn_records(monkeypatch, caplog, provider, key):
    import logging

    from app.core.config import get_settings

    monkeypatch.setenv("LLM_PROVIDER", provider)
    if key:
        monkeypatch.setenv("OPENAI_API_KEY", key)
    else:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()
    from app.core.embeddings import warn_if_fake_embeddings

    with caplog.at_level(logging.WARNING, logger="app.core.embeddings"):
        warn_if_fake_embeddings()
    get_settings.cache_clear()
    return [r for r in caplog.records if "fake embeddings" in r.getMessage()]


def test_warns_for_anthropic_without_openai_key(monkeypatch, caplog):
    assert _warn_records(monkeypatch, caplog, "anthropic", None)


def test_no_warning_with_openai_key(monkeypatch, caplog):
    assert not _warn_records(monkeypatch, caplog, "anthropic", "sk-test")


def test_no_warning_for_openai_provider(monkeypatch, caplog):
    assert not _warn_records(monkeypatch, caplog, "openai", None)
