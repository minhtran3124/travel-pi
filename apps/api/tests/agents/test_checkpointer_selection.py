"""Unit tests for checkpointer selection logic (Task 1.2 — conversation-persistence).

Asserts that a postgres-prefixed DATABASE_URL routes to AsyncPostgresSaver and any
non-postgres URL yields MemorySaver, without requiring a live database connection.
"""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

from langgraph.checkpoint.memory import MemorySaver


class _FakePostgresSaver:
    """Stand-in for AsyncPostgresSaver — tracks setup() calls, no real connection."""

    async def setup(self):
        pass


def _make_async_postgres_mock():
    """Build a mock AsyncPostgresSaver whose from_conn_string is an async CM."""
    fake_saver = _FakePostgresSaver()

    @asynccontextmanager
    async def _from_conn_string(dsn):
        yield fake_saver

    mock_cls = MagicMock()
    mock_cls.from_conn_string = _from_conn_string
    return mock_cls, fake_saver


def test_postgres_url_selects_async_postgres_saver():
    """A postgres-prefixed DATABASE_URL must yield AsyncPostgresSaver (not MemorySaver)."""
    from app.agents.checkpointer import open_checkpointer

    mock_cls, fake_saver = _make_async_postgres_mock()

    async def _run():
        with patch("langgraph.checkpoint.postgres.aio.AsyncPostgresSaver", mock_cls):
            async with open_checkpointer(
                "postgresql+psycopg://postgres:postgres@localhost:5432/travel"
            ) as cp:
                return cp

    result = asyncio.run(_run())
    assert isinstance(result, _FakePostgresSaver), (
        f"Expected _FakePostgresSaver (AsyncPostgresSaver stand-in), got {type(result)}"
    )


def test_non_postgres_url_yields_memory_saver():
    """A non-postgres DATABASE_URL must degrade to MemorySaver (no Postgres required)."""
    from app.agents.checkpointer import open_checkpointer

    async def _run():
        async with open_checkpointer("sqlite:///travel.db") as cp:
            return cp

    result = asyncio.run(_run())
    assert isinstance(result, MemorySaver), (
        f"Expected MemorySaver for sqlite URL, got {type(result)}"
    )


def test_postgres_prefix_variants_all_route_to_postgres_saver():
    """Both 'postgres://' and 'postgresql+psycopg://' prefixes select the durable path."""
    from app.agents.checkpointer import open_checkpointer

    urls = [
        "postgres://localhost/travel",
        "postgresql+psycopg://user:pw@localhost:5432/travel",
    ]

    for url in urls:
        mock_cls, fake_saver = _make_async_postgres_mock()

        async def _run(u=url, mc=mock_cls):
            with patch("langgraph.checkpoint.postgres.aio.AsyncPostgresSaver", mc):
                async with open_checkpointer(u) as cp:
                    return cp

        result = asyncio.run(_run())
        assert isinstance(result, _FakePostgresSaver), (
            f"URL {url!r} should select AsyncPostgresSaver, got {type(result)}"
        )
