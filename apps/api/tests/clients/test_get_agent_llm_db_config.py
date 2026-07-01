"""get_agent_llm DB-config fallback + base_url passthrough (Task A.6)."""

import pytest
from app.core.agent_config_cache import AgentConfigCache, AgentModelOverride


@pytest.fixture(autouse=True)
def _clear_cache():
    AgentConfigCache.clear()
    yield
    AgentConfigCache.clear()


def _capture_build_chat_model(monkeypatch):
    captured: dict = {}

    def fake(provider, model, *, temperature=None, base_url=None, **extra):
        captured["provider"] = provider
        captured["model"] = model
        captured["temperature"] = temperature
        captured["base_url"] = base_url
        captured["extra"] = extra
        from app.clients.llm import FakeLLM

        return FakeLLM()

    monkeypatch.setattr("app.clients.llm._build_chat_model", fake)
    return captured


def test_db_override_wins_over_env(monkeypatch):
    captured = _capture_build_chat_model(monkeypatch)
    AgentConfigCache.sync_from_cache(
        {"concierge": AgentModelOverride(provider="anthropic", model="claude-3")}
    )

    from app.clients.llm import get_agent_llm

    get_agent_llm("concierge")

    assert captured["provider"] == "anthropic"
    assert captured["model"] == "claude-3"


def test_per_field_fallback_provider_from_db_model_from_env(monkeypatch):
    captured = _capture_build_chat_model(monkeypatch)
    monkeypatch.setattr(
        "app.clients.llm.get_settings",
        lambda: type(
            "S",
            (),
            {
                "agent_llm_configs": {},
                "llm_provider": "openai",
                "llm_model": "gpt-4o",
                "fast_llm_model": "gpt-4o-mini",
                "llm_base_url": None,
            },
        )(),
    )
    AgentConfigCache.sync_from_cache(
        {"concierge": AgentModelOverride(provider="anthropic")}
    )

    from app.clients.llm import get_agent_llm

    get_agent_llm("concierge")

    assert captured["provider"] == "anthropic"
    assert captured["model"] == "gpt-4o"


def test_base_url_override_passed_through(monkeypatch):
    captured = _capture_build_chat_model(monkeypatch)
    AgentConfigCache.sync_from_cache(
        {"concierge": AgentModelOverride(base_url="https://custom.example.com")}
    )

    from app.clients.llm import get_agent_llm

    get_agent_llm("concierge")

    assert captured["base_url"] == "https://custom.example.com"


def test_no_cross_agent_leak(monkeypatch):
    captured = _capture_build_chat_model(monkeypatch)
    AgentConfigCache.sync_from_cache(
        {"concierge": AgentModelOverride(provider="anthropic", model="claude-3")}
    )

    from app.clients.llm import get_agent_llm

    get_agent_llm("planner")

    assert captured["provider"] != "anthropic"
    assert captured["model"] != "claude-3"


def test_empty_cache_matches_today_behavior(monkeypatch):
    captured = _capture_build_chat_model(monkeypatch)

    from app.clients.llm import get_agent_llm

    get_agent_llm("concierge")

    from app.core.config import get_settings

    s = get_settings()
    assert captured["provider"] == s.llm_provider
    assert captured["base_url"] == s.llm_base_url
