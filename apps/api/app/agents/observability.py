"""Langfuse tracing (specs/travel-agent Task 7.1).

When ``langfuse_enabled`` is set, every agent run is traced via Langfuse's
LangChain ``CallbackHandler``. Disabled by default, so tests and CI emit no
traces and need no keys. Trace metadata groups runs by user and by trip
(session_id = trip_id). Any init failure degrades to no tracing — the agent
keeps working.
"""

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

    Keyed on the four settings values so the same configuration always returns
    the same handler (built once), while a settings change (env change +
    ``get_settings.cache_clear()`` in tests) causes a cache miss and a fresh
    build.  Returns None when disabled or on any construction error.

    :param enabled: Whether Langfuse tracing is enabled.
    :param public_key: Langfuse public key.
    :param secret_key: Langfuse secret key.
    :param host: Langfuse host URL.
    :return: A configured ``CallbackHandler``, or ``None`` when disabled or
        construction fails.
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
    """Return a Langfuse CallbackHandler, or None when disabled / unconfigured.

    :return: A configured ``CallbackHandler``, or ``None``.
    """
    s = get_settings()
    return _build_handler(
        s.langfuse_enabled,
        s.langfuse_public_key,
        s.langfuse_secret_key,
        s.langfuse_host,
    )


def callbacks() -> list:
    """Return the callbacks list for a graph run ([] when tracing is off).

    :return: A single-item list with the Langfuse handler, or ``[]``.
    """
    handler = build_langfuse_handler()
    return [handler] if handler is not None else []


def trace_metadata(
    user_id: str, session_id: str | None, tags: list[str] | None = None
) -> dict:
    """Langfuse run metadata: group traces by user and trip.

    :param user_id: The authenticated user's id.
    :param session_id: The trip id, used as the Langfuse session id.
    :param tags: Extra Langfuse tags; defaults to ``["travel-agent"]``.
    :return: The Langfuse metadata dict for this run.
    """
    return {
        "langfuse_user_id": user_id,
        "langfuse_session_id": session_id or "none",
        "langfuse_tags": tags or ["travel-agent"],
    }
