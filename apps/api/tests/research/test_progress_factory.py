"""``make_progress_bus`` keeps the zero-config default: in-process unless REDIS_URL is set."""

from __future__ import annotations

from types import SimpleNamespace

from app.research import progress
from app.research.progress import ProgressBus, RedisProgressBus, make_progress_bus


def _settings(monkeypatch, url):
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: SimpleNamespace(redis_url=url, research_timeout_s=600),
    )


def test_in_process_bus_without_redis_url(monkeypatch) -> None:
    _settings(monkeypatch, None)
    bus = make_progress_bus()
    assert type(bus) is ProgressBus


def test_redis_bus_with_redis_url(monkeypatch) -> None:
    _settings(monkeypatch, "redis://localhost:6379/0")
    bus = make_progress_bus()
    assert isinstance(bus, RedisProgressBus)
    assert progress.RedisProgressBus is RedisProgressBus
