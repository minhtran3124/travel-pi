"""Alembic round-trip coverage for the agent_run_steps migration."""

from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

API_ROOT = Path(__file__).resolve().parents[2]
REVISION = "b2d9f4a7c1e8"
DOWN_REVISION = "e3b7c5d9a1f4"
INDEX = "ix_agent_run_steps_run_id"


def _isolated_migration_url(
    tmp_db: str, tmp_path: Path
) -> tuple[str, Callable[[], None]]:
    """Return an isolated SQLite DB or Postgres schema for destructive DDL."""
    url = make_url(tmp_db)
    if url.get_backend_name() != "postgresql":
        return f"sqlite:///{tmp_path / 'agent_run_steps_migration.db'}", lambda: None

    schema = f"test_agent_run_steps_migration_{uuid4().hex}"
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


def _agent_runs_columns(engine) -> set[str]:
    return {column["name"] for column in inspect(engine).get_columns("agent_runs")}


def _step_indexes(engine) -> set[str]:
    return {index["name"] for index in inspect(engine).get_indexes("agent_run_steps")}


def test_agent_run_steps_migration_upgrade_downgrade_round_trip(
    tmp_db, tmp_path, monkeypatch
):
    database_url, cleanup = _isolated_migration_url(tmp_db, tmp_path)
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = _alembic_config()
    engine = create_engine(database_url, future=True)

    try:
        command.upgrade(config, DOWN_REVISION)
        assert inspect(engine).has_table("agent_run_steps") is False
        assert "prompt_versions" not in _agent_runs_columns(engine)

        command.upgrade(config, REVISION)
        assert inspect(engine).has_table("agent_run_steps") is True
        assert INDEX in _step_indexes(engine)
        assert "prompt_versions" in _agent_runs_columns(engine)

        command.downgrade(config, DOWN_REVISION)
        assert inspect(engine).has_table("agent_run_steps") is False
        assert "prompt_versions" not in _agent_runs_columns(engine)

        # Re-upgrade is clean (idempotent create).
        command.upgrade(config, REVISION)
        assert inspect(engine).has_table("agent_run_steps") is True
        assert "prompt_versions" in _agent_runs_columns(engine)
    finally:
        engine.dispose()
        cleanup()
        get_settings.cache_clear()
