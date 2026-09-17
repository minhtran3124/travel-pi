"""Embedding model selection for the agent-memory semantic index: OpenAI when keyed, a deterministic fake otherwise (no key or network in dev/test)."""

from __future__ import annotations

from langchain_core.embeddings import DeterministicFakeEmbedding, Embeddings

from app.core.config import get_settings

EMBED_DIM = 1536  # text-embedding-3-small dim
_FAKE_EMBED_DIM = EMBED_DIM  # the fake matches so dims are stable across modes


def get_embeddings() -> Embeddings:
    """Return the embedding model: OpenAI when keyed, deterministic fake otherwise."""
    s = get_settings()
    if s.openai_api_key:
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=s.embedding_model, api_key=s.openai_api_key)
    return DeterministicFakeEmbedding(size=_FAKE_EMBED_DIM)
