"""Alembic round-trip coverage for the feedback_events + messages.agent_run_id migration."""

from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

API_ROOT = Path(__file__).resolve().parents[2]
REVISION = "d4f7a2c9e1b3"
DOWN_REVISION = "b8e4c1f7a305"
TABLE = "feedback_events"
LINK_TABLE = "messages"
LINK_COLUMN = "agent_run_id"
LINK_INDEX = "ix_messages_agent_run_id"
COLUMNS = {
    "id",
    "created_at",
    "updated_at",
    "schema_version",
    "user_id",
    "conversation_id",
    "assistant_message_id",
    "agent_run_id",
    "action",
    "rating",
    "reason_code",
    "comment",
    "source",
    "locale",
    "client_event_id",
    "request_fingerprint",
    "supersedes_event_id",
}
INDEXES = {
    "ix_feedback_events_user_id": ("user_id",),
    "ix_feedback_events_conversation_id": ("conversation_id",),
    "ix_feedback_events_assistant_message_id": ("assistant_message_id",),
    "ix_feedback_events_agent_run_id": ("agent_run_id",),
    "ix_feedback_events_assistant_message_id_created_at_id": (
        "assistant_message_id",
        "created_at",
        "id",
    ),
    "ix_feedback_events_user_id_created_at": ("user_id", "created_at"),
    "ix_feedback_events_rating_created_at": ("rating", "created_at"),
}
INSERT = text(
    "INSERT INTO feedback_events (id, created_at, updated_at, schema_version, "
    "user_id, conversation_id, assistant_message_id, action, rating, source, "
    "client_event_id, request_fingerprint) VALUES (:id, :ts, :ts, 1, :user, "
    "'conv-1', 'msg-1', 'set_rating', :rating, 'chat_message_actions', "
    ":client_event_id, 'fp')"
)


def _isolated_migration_url(
    tmp_db: str, tmp_path: Path
) -> tuple[str, Callable[[], None]]:
    """Return an isolated SQLite DB or Postgres schema for destructive DDL."""
    url = make_url(tmp_db)
    if url.get_backend_name() != "postgresql":
        return f"sqlite:///{tmp_path / 'feedback_events_migration.db'}", (lambda: None)

    schema = f"test_feedback_events_{uuid4().hex}"
    admin_engine = create_engine(tmp_db, future=True)
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    separator = "&" if "?" in tmp_db else "?"
    isolated = f"{tmp_db}{separator}options=-csearch_path={schema}"

    def cleanup() -> None:
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()

    return isolated, cleanup


def _assert_upgraded(engine) -> None:
    inspector = inspect(engine)
    assert LINK_COLUMN in {c["name"] for c in inspector.get_columns(LINK_TABLE)}
    assert LINK_INDEX in {ix["name"] for ix in inspector.get_indexes(LINK_TABLE)}
    assert inspector.has_table(TABLE) is True
    assert {c["name"] for c in inspector.get_columns(TABLE)} == COLUMNS
    unique = {
        c["name"]: tuple(c["column_names"])
        for c in inspector.get_unique_constraints(TABLE)
    }
    assert unique["uq_feedback_events_user_client_event"] == (
        "user_id",
        "client_event_id",
    )
    indexes = {
        ix["name"]: tuple(ix["column_names"])
        for ix in inspector.get_indexes(TABLE)
        if not ix.get("duplicates_constraint")
    }
    assert indexes == INDEXES


def _assert_downgraded(engine) -> None:
    inspector = inspect(engine)
    assert inspector.has_table(TABLE) is False
    assert LINK_COLUMN not in {c["name"] for c in inspector.get_columns(LINK_TABLE)}
    assert LINK_INDEX not in {ix["name"] for ix in inspector.get_indexes(LINK_TABLE)}
    assert inspector.has_table("agent_runs") is True
    assert inspector.has_table("agent_run_steps") is True


def test_feedback_events_migration_round_trip(tmp_db, tmp_path, monkeypatch):
    database_url, cleanup = _isolated_migration_url(tmp_db, tmp_path)
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(str(API_ROOT / "alembic.ini"))
    engine = create_engine(database_url, future=True)

    try:
        command.upgrade(config, DOWN_REVISION)
        _assert_downgraded(engine)

        command.upgrade(config, REVISION)
        _assert_upgraded(engine)

        # The rating CHECK and the (user_id, client_event_id) unique key are live.
        row = {"id": "ev-1", "ts": "2026-09-12T00:00:00+00:00", "user": "u-1"}
        with engine.begin() as connection:
            connection.execute(INSERT, {**row, "rating": 1, "client_event_id": "ce-1"})
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                INSERT, {**row, "id": "ev-2", "rating": 0, "client_event_id": "ce-2"}
            )
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                INSERT, {**row, "id": "ev-3", "rating": -1, "client_event_id": "ce-1"}
            )

        command.downgrade(config, DOWN_REVISION)
        _assert_downgraded(engine)

        command.upgrade(config, REVISION)
        _assert_upgraded(engine)
    finally:
        engine.dispose()
        cleanup()
        get_settings.cache_clear()
