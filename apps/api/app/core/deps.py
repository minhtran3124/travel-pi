"""Shared FastAPI dependencies for the agent layer (specs/travel-agent Task 1.1).

``get_llm_client`` is the seam the agent router resolves a chat model through.
Following the project's DI convention (``app.db.session.get_session``), callers
take it via ``Depends`` and tests swap it with ``app.dependency_overrides`` — a
``FakeLLM`` in tests — instead of binding a module-level singleton. This avoids
the singleton/test-isolation footgun the di-session refactor removed elsewhere.
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from app.clients.llm import get_llm


def get_llm_client() -> BaseChatModel:
    """Return the configured chat model. Overridable in tests via DI."""
    return get_llm()
