"""Bot identity resolution: instance id precedence, role, display name."""

import socket

import pytest
from app.core.instance import resolve_identity


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ("BOT_INSTANCE_ID", "RENDER_INSTANCE_ID", "BOT_ROLE", "BOT_NAME"):
        monkeypatch.delenv(name, raising=False)


def test_defaults_to_hostname_and_web_role():
    ident = resolve_identity()
    assert ident.instance_id == socket.gethostname()
    assert ident.role == "web"
    assert ident.name is None


def test_render_instance_id_beats_hostname(monkeypatch):
    monkeypatch.setenv("RENDER_INSTANCE_ID", "srv-render")
    assert resolve_identity().instance_id == "srv-render"


def test_bot_instance_id_beats_render(monkeypatch):
    monkeypatch.setenv("RENDER_INSTANCE_ID", "srv-render")
    monkeypatch.setenv("BOT_INSTANCE_ID", "api-1")
    assert resolve_identity().instance_id == "api-1"


def test_blank_env_is_ignored(monkeypatch):
    monkeypatch.setenv("BOT_INSTANCE_ID", "  ")
    assert resolve_identity().instance_id == socket.gethostname()


def test_worker_role_from_env_and_argument(monkeypatch):
    monkeypatch.setenv("BOT_ROLE", "worker")
    assert resolve_identity().role == "worker"
    assert resolve_identity("web").role == "web"


def test_unknown_role_falls_back_to_web(monkeypatch):
    monkeypatch.setenv("BOT_ROLE", "cron")
    assert resolve_identity().role == "web"


def test_display_name(monkeypatch):
    monkeypatch.setenv("BOT_NAME", "Api One")
    assert resolve_identity().name == "Api One"
