"""Embedding provider selection + graceful degradation (#270).

A dead embedding key (e.g. an exhausted OpenAI quota under LLM_PROVIDER=anthropic)
must degrade to non-semantic vectors once, not raise on every memory call or
hammer the provider with retries.
"""

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding, Embeddings


class _DeadEmbeddings(Embeddings):
    def __init__(self) -> None:
        self.calls = 0

    def embed_documents(self, texts):
        self.calls += 1
        raise RuntimeError("429 insufficient_quota")

    def embed_query(self, text):
        self.calls += 1
        raise RuntimeError("429 insufficient_quota")


def _resilient(primary, now=lambda: 0.0):
    from app.core.embeddings import EMBED_DIM, ResilientEmbeddings

    return ResilientEmbeddings(
        primary, DeterministicFakeEmbedding(size=EMBED_DIM), clock=now
    )


def test_failure_falls_back_instead_of_raising():
    emb = _resilient(_DeadEmbeddings())
    vec = emb.embed_query("tokyo")
    assert len(vec) == 1536
    assert len(emb.embed_documents(["a", "b"])) == 2


def test_no_retry_storm_circuit_stays_open_during_cooldown():
    primary = _DeadEmbeddings()
    t = [0.0]
    emb = _resilient(primary, now=lambda: t[0])
    for _ in range(5):
        emb.embed_query("x")
    assert primary.calls == 1
    t[0] = 10_000.0  # cooldown elapsed -> primary probed again
    emb.embed_query("x")
    assert primary.calls == 2


@pytest.mark.asyncio
async def test_async_path_degrades_too():
    primary = _DeadEmbeddings()
    emb = _resilient(primary)
    assert len(await emb.aembed_query("x")) == 1536
    assert len(await emb.aembed_documents(["x"])) == 1
    assert primary.calls == 1


def test_embedding_provider_fake_ignores_openai_key(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("OPENAI_API_KEY", "sk-dead")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fake")
    get_settings.cache_clear()
    from app.core.embeddings import get_embeddings

    assert isinstance(get_embeddings(), DeterministicFakeEmbedding)
    get_settings.cache_clear()


def test_embedding_provider_auto_with_key_is_wrapped(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("OPENAI_API_KEY", "sk-dead")
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    get_settings.cache_clear()
    from app.core.embeddings import ResilientEmbeddings, get_embeddings

    assert isinstance(get_embeddings(), ResilientEmbeddings)
    get_settings.cache_clear()


def test_unknown_embedding_provider_rejected(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("EMBEDDING_PROVIDER", "bogus")
    with pytest.raises(ValueError):
        Settings()
