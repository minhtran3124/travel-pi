"""Graph checkpointer selection (specs/travel-agent Task 2.1).

The checkpointer is what makes the agent stateful across turns and sessions:
LangGraph snapshots graph state per ``thread_id`` after every node. We mirror the
app's existing engine split — SQLite locally / in tests, Postgres in docker —
and fall back to an in-memory saver if the chosen backend can't be initialised
(so a missing Postgres never takes the whole app down, matching the reference
chatbot's degrade-to-MemorySaver behaviour).

Sync savers are used: FastAPI runs sync handlers in a threadpool and the agent
graph is invoked from there. A real Postgres deployment can swap to the async
saver in lifespan; the selection seam lives here.
"""

from __future__ import annotations

import logging
import sqlite3

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _sqlite_path(url: str) -> str:
    """Extract the file path (or ``:memory:``) from a SQLAlchemy sqlite URL."""
    # "sqlite:///travel.db" -> "travel.db"; "sqlite:///:memory:" -> ":memory:";
    # "sqlite://" (no path) -> ":memory:".
    tail = url.split("sqlite://", 1)[-1].lstrip("/")
    return tail or ":memory:"


def get_checkpointer(database_url: str | None = None) -> BaseCheckpointSaver:
    """Return a checkpointer for the configured backend.

    SQLite -> ``SqliteSaver`` (tables created via ``setup()``). Postgres ->
    ``PostgresSaver``. Anything that fails to initialise -> ``MemorySaver``.
    """
    url = database_url or get_settings().database_url
    try:
        if url.startswith("sqlite"):
            conn = sqlite3.connect(_sqlite_path(url), check_same_thread=False)
            saver = SqliteSaver(conn)
            saver.setup()
            return saver
        if url.startswith("postgres"):
            # Imported lazily so the SQLite path never needs psycopg.
            from langgraph.checkpoint.postgres import PostgresSaver

            saver = PostgresSaver.from_conn_string(url).__enter__()
            saver.setup()
            return saver
    except Exception:
        logger.exception("Checkpointer init failed for %s; using MemorySaver", url)
        return MemorySaver()
    logger.warning("Unrecognised DATABASE_URL %r; using MemorySaver", url)
    return MemorySaver()
