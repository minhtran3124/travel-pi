"""Langfuse tracing (specs/travel-agent Task 7.1).

When ``langfuse_enabled`` is set, every agent run is traced via Langfuse's
LangChain ``CallbackHandler``. Disabled by default, so tests and CI emit no
traces and need no keys. Trace metadata groups runs by user and by trip
(session_id = trip_id). Any init failure degrades to no tracing — the agent
keeps working.
"""

from __future__ import annotations

import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def build_langfuse_handler():
    """Return a Langfuse CallbackHandler, or None when disabled / unconfigured."""
    s = get_settings()
    if not s.langfuse_enabled:
        return None
    try:
        from langfuse import Langfuse
        from langfuse.langchain import CallbackHandler

        # Configure the process-wide client (no network at construction).
        Langfuse(
            public_key=s.langfuse_public_key,
            secret_key=s.langfuse_secret_key,
            host=s.langfuse_host,
        )
        return CallbackHandler(public_key=s.langfuse_public_key)
    except Exception:
        logger.exception("Langfuse init failed; continuing without tracing")
        return None


def callbacks() -> list:
    """Return the callbacks list for a graph run ([] when tracing is off)."""
    handler = build_langfuse_handler()
    return [handler] if handler is not None else []


def trace_metadata(
    user_id: str, session_id: str | None, tags: list[str] | None = None
) -> dict:
    """Langfuse run metadata: group traces by user and trip."""
    return {
        "langfuse_user_id": user_id,
        "langfuse_session_id": session_id or "none",
        "langfuse_tags": tags or ["travel-agent"],
    }
