"""Alembic round-trip coverage for the agent_runs migration."""

from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

API_ROOT = Path(__file__).resolve().parents[2]
REVISION = "e3b7c5d9a1f4"
DOWN_REVISION = "c7f1a9d4e6b2"
INDEXES = {
    "ix_agent_runs_user_id",
    "ix_agent_runs_conversation_id",
    "ix_agent_runs_status",
}


def _isolated_migration_url(
    tmp_db: str, tmp_path: Path
) -> tuple[str, Callable[[], None]]:
    """Return an isolated SQLite DB or Postgres schema for destructive DDL."""
    url = make_url(tmp_db)
    if url.get_backend_name() != "postgresql":
        return f"sqlite:///{tmp_path / 'agent_runs_migration.db'}", lambda: None

    schema = f"test_agent_runs_migration_{uuid4().hex}"
    admin_engine = create_engine(tmp_db, future=True)
    with admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    # Keep libpq ``options`` raw (see test_rate_limit_migration: render_as_string() percent-encoding breaks Alembic's ConfigParser).
    separator = "&" if "?" in tmp_db else "?"
    isolated = f"{tmp_db}{separator}options=-csearch_path={schema}"

    def cleanup() -> None:
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin_engine.dispose()

    return isolated, cleanup


def _alembic_config() -> Config:
    return Config(str(API_ROOT / "alembic.ini"))


def _indexes(engine) -> set[str]:
    inspector = inspect(engine)
    return {index["name"] for index in inspector.get_indexes("agent_runs")}


def test_agent_runs_migration_upgrade_downgrade_round_trip(
    tmp_db, tmp_path, monkeypatch
):
    database_url, cleanup = _isolated_migration_url(tmp_db, tmp_path)
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = _alembic_config()
    engine = create_engine(database_url, future=True)

    try:
        command.upgrade(config, DOWN_REVISION)
        assert inspect(engine).has_table("agent_runs") is False

        command.upgrade(config, REVISION)
        assert inspect(engine).has_table("agent_runs") is True
        assert INDEXES.issubset(_indexes(engine))

        command.downgrade(config, DOWN_REVISION)
        assert inspect(engine).has_table("agent_runs") is False

        # Re-upgrade is clean (idempotent create).
        command.upgrade(config, REVISION)
        assert inspect(engine).has_table("agent_runs") is True
    finally:
        engine.dispose()
        cleanup()
        get_settings.cache_clear()


def test_instance_id_migration_adds_nullable_column_and_reverts(
    tmp_db, tmp_path, monkeypatch
):
    database_url, cleanup = _isolated_migration_url(tmp_db, tmp_path)
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = _alembic_config()
    engine = create_engine(database_url, future=True)

    def _cols() -> dict:
        return {c["name"]: c for c in inspect(engine).get_columns("agent_runs")}

    try:
        command.upgrade(config, "c5a8e1d3f7b9")
        assert "instance_id" not in _cols()

        command.upgrade(config, "head")
        assert _cols()["instance_id"]["nullable"] is True

        command.downgrade(config, "-1")
        assert "instance_id" not in _cols()
    finally:
        engine.dispose()
        cleanup()
        get_settings.cache_clear()
