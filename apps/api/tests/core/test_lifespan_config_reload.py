"""Lifespan startup populates AgentConfigCache from the DB (Task A.7)."""

from app.core import config
from app.core.agent_config_cache import AgentConfigCache
from app.data.agent_config import AGENT_CONFIG_NODES
from app.main import create_app
from fastapi.testclient import TestClient


def _app_on_temp_db(monkeypatch, tmp_path):
    url = f"sqlite:///{tmp_path / 'lifespan.db'}"
    settings = config.get_settings()
    monkeypatch.setattr(settings, "database_url", url, raising=False)
    config.get_settings.cache_clear()
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    return create_app()


def test_lifespan_populates_cache_from_seeded_rows(monkeypatch, tmp_path):
    AgentConfigCache.clear()
    app = _app_on_temp_db(monkeypatch, tmp_path)

    with TestClient(app):
        for name in AGENT_CONFIG_NODES:
            assert AgentConfigCache.get(name) is not None

    AgentConfigCache.clear()
