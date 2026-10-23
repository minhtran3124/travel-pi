"""Embedding model selection for the agent-memory semantic index: OpenAI when keyed, a deterministic fake otherwise (no key or network in dev/test)."""

from __future__ import annotations

import logging

from langchain_core.embeddings import DeterministicFakeEmbedding, Embeddings

from app.core.config import get_settings
from app.core.llm_providers import get_provider

logger = logging.getLogger(__name__)

EMBED_DIM = 1536  # text-embedding-3-small dim
_FAKE_EMBED_DIM = EMBED_DIM  # the fake matches so dims are stable across modes


def get_embeddings() -> Embeddings:
    """Return the embedding model: OpenAI when keyed, deterministic fake otherwise."""
    s = get_settings()
    if s.openai_api_key:
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=s.embedding_model, api_key=s.openai_api_key)
    return DeterministicFakeEmbedding(size=_FAKE_EMBED_DIM)


def warn_if_fake_embeddings() -> None:
    """Log a WARNING (call once at startup) when a non-OpenAI provider runs without an OpenAI key.

    Embeddings are OpenAI-only, so memory semantic search silently falls back to the fake model.
    """
    s = get_settings()
    profile = get_provider(s.llm_provider)
    if profile is not None and profile.sdk == "openai":
        return
    if not s.openai_api_key:
        logger.warning(
            "LLM_PROVIDER=%s and OPENAI_API_KEY is unset: memory semantic search uses fake embeddings",
            s.llm_provider,
        )
