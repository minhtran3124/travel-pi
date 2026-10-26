"""Embedding model selection for the agent-memory semantic index: OpenAI when keyed, a deterministic fake otherwise (no key or network in dev/test).

``EMBEDDING_PROVIDER`` (``auto`` | ``openai`` | ``fake``) picks the source. A keyed OpenAI model is wrapped in :class:`ResilientEmbeddings`, so a dead key (exhausted quota, revoked) degrades to non-semantic fake vectors instead of raising on every memory call.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from langchain_core.embeddings import DeterministicFakeEmbedding, Embeddings

from app.core.config import get_settings
from app.core.llm_providers import get_provider

logger = logging.getLogger(__name__)

EMBED_DIM = 1536  # text-embedding-3-small dim
_FAKE_EMBED_DIM = EMBED_DIM  # the fake matches so dims are stable across modes

#: Seconds the primary stays bypassed after a failure before it is probed again.
_COOLDOWN_SECONDS = 300.0


class ResilientEmbeddings(Embeddings):
    """Primary embeddings with a circuit breaker onto a fallback.

    The first primary failure opens the circuit: every call goes straight to the fallback (no retry storm against a dead key) until the cooldown elapses, then the primary is probed once more. Fallback vectors are non-semantic, so search ranking degrades but nothing raises.
    """

    def __init__(
        self,
        primary: Embeddings,
        fallback: Embeddings,
        *,
        cooldown: float = _COOLDOWN_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._cooldown = cooldown
        self._clock = clock
        self._open_until: float | None = None

    def _is_open(self) -> bool:
        return self._open_until is not None and self._clock() < self._open_until

    def _trip(self, exc: Exception) -> None:
        self._open_until = self._clock() + self._cooldown
        logger.warning(
            "embeddings unavailable (%s); using non-semantic fallback for %.0fs",
            type(exc).__name__,
            self._cooldown,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not self._is_open():
            try:
                return self._primary.embed_documents(texts)
            except Exception as exc:  # noqa: BLE001 - any provider failure degrades
                self._trip(exc)
        return self._fallback.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        if not self._is_open():
            try:
                return self._primary.embed_query(text)
            except Exception as exc:  # noqa: BLE001 - any provider failure degrades
                self._trip(exc)
        return self._fallback.embed_query(text)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        if not self._is_open():
            try:
                return await self._primary.aembed_documents(texts)
            except Exception as exc:  # noqa: BLE001 - any provider failure degrades
                self._trip(exc)
        return await self._fallback.aembed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        if not self._is_open():
            try:
                return await self._primary.aembed_query(text)
            except Exception as exc:  # noqa: BLE001 - any provider failure degrades
                self._trip(exc)
        return await self._fallback.aembed_query(text)


def get_embeddings() -> Embeddings:
    """Return the embedding model per ``EMBEDDING_PROVIDER``: OpenAI (degrading to fake on failure) when keyed, deterministic fake otherwise."""
    s = get_settings()
    fake = DeterministicFakeEmbedding(size=_FAKE_EMBED_DIM)
    if s.embedding_provider == "fake" or not s.openai_api_key:
        if s.embedding_provider == "openai":
            logger.warning(
                "EMBEDDING_PROVIDER=openai but OPENAI_API_KEY is unset: using fake embeddings"
            )
        return fake

    from langchain_openai import OpenAIEmbeddings

    # max_retries=0: the breaker (not the SDK) owns failure handling, so a dead key costs one call.
    primary = OpenAIEmbeddings(
        model=s.embedding_model, api_key=s.openai_api_key, max_retries=0
    )
    return ResilientEmbeddings(primary, fake)


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
