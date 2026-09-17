"""Langfuse tracing: disabled by default; any init failure degrades to no tracing."""

from __future__ import annotations

import logging
from functools import cache

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@cache
def _build_handler(
    enabled: bool,
    public_key: str | None,
    secret_key: str | None,
    host: str,
):
    """Build the Langfuse client + handler once per unique settings combination.

    Keyed on the settings values so a config change causes a cache miss and a fresh
    build; returns None when disabled or on any construction error.
    """
    if not enabled:
        return None
    try:
        from langfuse import Langfuse
        from langfuse.langchain import CallbackHandler

        # Configure the process-wide client (no network at construction).
        Langfuse(public_key=public_key, secret_key=secret_key, host=host)
        return CallbackHandler(public_key=public_key)
    except Exception:
        logger.exception("Langfuse init failed; continuing without tracing")
        return None


def build_langfuse_handler():
    """Return a Langfuse CallbackHandler, or None when disabled / unconfigured."""
    s = get_settings()
    return _build_handler(
        s.langfuse_enabled,
        s.langfuse_public_key,
        s.langfuse_secret_key,
        s.langfuse_host,
    )


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
