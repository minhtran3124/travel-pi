"""Graph checkpointer selection: async Postgres saver, else in-memory MemorySaver."""

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
    """Yield the agent checkpointer for the app's lifetime (``lifespan``-managed)."""
    url = database_url or get_settings().database_url
    if url.startswith("postgres"):
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            async with AsyncPostgresSaver.from_conn_string(_libpq_dsn(url)) as saver:
                await saver.setup()
                yield saver
            return
        except Exception as exc:
            # Configured-but-unreachable Postgres silently drops to ephemeral state:
            # fail fast in production, degrade loudly in dev/test.
            if get_settings().is_production:
                logger.critical(
                    "AsyncPostgresSaver init failed for %s in production; "
                    "refusing to start on an ephemeral checkpointer.",
                    url,
                )
                raise
            logger.warning(
                "Postgres checkpointer unreachable (%s): %s. Falling back to an "
                "EPHEMERAL in-memory checkpointer — agent conversation history "
                "will NOT survive a restart. Start the dev DB with "
                "`cd apps/api && docker compose up -d db` to persist it.",
                url,
                exc,
            )
    yield MemorySaver()


def get_checkpointer(database_url: str | None = None) -> BaseCheckpointSaver:
    """In-memory saver for tests / non-Postgres degrade."""
    return MemorySaver()
