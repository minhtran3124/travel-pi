"""Alembic round-trip coverage for the bot_heartbeats migration (SQLite; Postgres schema when TEST_DATABASE_URL is set)."""

from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

API_ROOT = Path(__file__).resolve().parents[2]
REVISION = "c5a8e1d3f7b9"
DOWN_REVISION = "a7c1e9d3b5f2"


def _isolated_migration_url(
    tmp_db: str, tmp_path: Path
) -> tuple[str, Callable[[], None]]:
    """Return an isolated SQLite DB or Postgres schema for destructive DDL."""
    url = make_url(tmp_db)
    if url.get_backend_name() != "postgresql":
        return f"sqlite:///{tmp_path / 'bot_heartbeats_migration.db'}", lambda: None

    schema = f"test_bot_heartbeats_migration_{uuid4().hex}"
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


def test_bot_heartbeats_upgrade_downgrade_round_trip(tmp_db, tmp_path, monkeypatch):
    database_url, cleanup = _isolated_migration_url(tmp_db, tmp_path)
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = Config(str(API_ROOT / "alembic.ini"))
    engine = create_engine(database_url, future=True)

    try:
        command.upgrade(config, DOWN_REVISION)
        assert inspect(engine).has_table("bot_heartbeats") is False

        command.upgrade(config, REVISION)
        inspector = inspect(engine)
        assert inspector.has_table("bot_heartbeats") is True
        assert {c["name"] for c in inspector.get_columns("bot_heartbeats")} == {
            "instance_id",
            "pid",
            "role",
            "host",
            "started_at",
            "last_seen",
            "snapshot",
        }
        assert inspector.get_pk_constraint("bot_heartbeats")["constrained_columns"] == [
            "instance_id",
            "pid",
        ]

        command.downgrade(config, DOWN_REVISION)
        assert inspect(engine).has_table("bot_heartbeats") is False
    finally:
        engine.dispose()
        get_settings.cache_clear()
        cleanup()
