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

    from app.clients.llm import get_agent_llm

    get_agent_llm("concierge")

    assert captured["provider"] == "openai"
    # The empty-cache shortcut delegates to get_llm(), which does not pass
    # base_url explicitly — _build_chat_model applies its own env fallback
    # (see test_build_chat_model_falls_back_to_settings_base_url below),
    # so this level only sees the unset param.
    assert captured["base_url"] is None


def test_empty_cache_fast_agent_uses_fast_model(monkeypatch):
    captured = _capture_build_chat_model(monkeypatch)

    from app.clients.llm import get_agent_llm

    get_agent_llm("journal")

    from app.core.config import get_settings

    s = get_settings()
    assert captured["model"] == s.fast_llm_model


def test_build_chat_model_falls_back_to_settings_base_url(monkeypatch):
    # One level deeper than the get_agent_llm tests above: verifies
    # _build_chat_model's own `base_url or s.llm_base_url` fallback, which
    # get_agent_llm's empty-cache shortcut relies on implicitly (it never
    # passes base_url itself).
    captured: dict = {}

    def fake_init_chat_model(model, *, model_provider, **kwargs):
        captured["base_url"] = kwargs.get("base_url")
        from app.clients.llm import FakeLLM

        return FakeLLM()

    monkeypatch.setattr("app.clients.llm.init_chat_model", fake_init_chat_model)
    monkeypatch.setattr(
        "app.clients.llm.get_settings",
        lambda: type(
            "S",
            (),
            {"llm_base_url": "https://ambient-base-url.example.com"},
        )(),
    )

    from app.clients.llm import _build_chat_model

    _build_chat_model("openai", "gpt-4o")

    assert captured["base_url"] == "https://ambient-base-url.example.com"
