"""Graph checkpointer selection (specs/travel-agent Task 2.1; agent-graph-lifecycle).

The checkpointer is what makes the agent stateful across turns and sessions:
LangGraph snapshots graph state per ``thread_id`` after every node.

Per ``specs/agent-graph-lifecycle`` (E001) the durable backend is **Postgres only**,
via the **async** saver: ``open_checkpointer`` is an async context manager entered once
in the app ``lifespan`` and held open for the process lifetime — never per request. Any
non-Postgres URL (local dev / the SQLite test suite) or an init failure degrades to an
in-memory ``MemorySaver`` so a missing Postgres never blocks startup; tests inject their
own ``MemorySaver`` directly.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _libpq_dsn(url: str) -> str:
    """Strip SQLAlchemy's ``+driver`` so psycopg/libpq accepts the DSN."""
    return url.replace("postgresql+psycopg://", "postgresql://").replace(
        "postgres+psycopg://", "postgresql://"
    )


@asynccontextmanager
async def open_checkpointer(
    database_url: str | None = None,
) -> AsyncIterator[BaseCheckpointSaver]:
    """Yield the agent checkpointer for the app's lifetime (``lifespan``-managed).

    Postgres URL -> ``AsyncPostgresSaver`` (tables created via ``setup()``), opened
    once with ``async with`` and closed on shutdown. Anything else, or any init
    failure -> ``MemorySaver``.
    """
    url = database_url or get_settings().database_url
    if url.startswith("postgres"):
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            async with AsyncPostgresSaver.from_conn_string(_libpq_dsn(url)) as saver:
                await saver.setup()
                yield saver
            return
        except Exception:
            logger.exception(
                "AsyncPostgresSaver init failed for %s; using MemorySaver", url
            )
    yield MemorySaver()


def get_checkpointer(database_url: str | None = None) -> BaseCheckpointSaver:
    """In-memory saver for tests / non-Postgres degrade.

    Production code builds the durable saver through :func:`open_checkpointer` so its
    connection is lifecycle-managed; this sync helper exists only for the ephemeral
    in-memory case.
    """
    return MemorySaver()
