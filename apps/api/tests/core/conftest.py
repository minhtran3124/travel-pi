"""Fixtures for tests of ``Settings`` defaults."""

from __future__ import annotations

import os

import pytest
from app.core.config import Settings, get_settings


@pytest.fixture
def isolated_settings_env(monkeypatch, tmp_path):
    """Run with no ``.env`` in the cwd and no ``Settings`` env var set, so defaults are the real defaults.

    ``Settings`` reads ``.env`` from the cwd, so a developer's real keys would otherwise
    leak into tests that assert "no key by default".
    """
    monkeypatch.chdir(tmp_path)
    fields = {name.upper() for name in Settings.model_fields}
    for var in [v for v in os.environ if v.upper() in fields]:
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
