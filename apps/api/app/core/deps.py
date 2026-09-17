"""Shared FastAPI dependency for resolving the agent's chat model, overridable in tests via ``app.dependency_overrides`` (a ``FakeLLM``) instead of a module-level singleton."""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from app.clients.llm import get_llm


def get_llm_client() -> BaseChatModel:
    """Return the configured chat model. Overridable in tests via DI."""
    return get_llm()
