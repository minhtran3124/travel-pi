"""``--provider`` for the keyed entrypoints (specs/anthropic-provider T8)."""

from __future__ import annotations

import pytest
from app.core.agent_config_cache import AgentConfigCache, AgentModelOverride
from app.core.config import get_settings
from eval.provider import (
    apply_provider,
    extract_provider,
    pin_agent_config_to_provider,
)


def test_extract_provider_strips_flag_both_forms(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert extract_provider(["--suite", "smoke", "--provider", "anthropic"]) == (
        "anthropic",
        ["--suite", "smoke"],
    )
    assert extract_provider(["--provider=openai", "--dry-run"]) == (
        "openai",
        ["--dry-run"],
    )
    assert extract_provider(["--suite", "smoke"]) == (None, ["--suite", "smoke"])


def test_extract_provider_honours_non_default_env_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert extract_provider(["--suite", "smoke"]) == ("anthropic", ["--suite", "smoke"])
    monkeypatch.setenv(
        "LLM_PROVIDER", "openai"
    )  # the default: no pin, DB config untouched
    assert extract_provider(["--suite", "smoke"]) == (None, ["--suite", "smoke"])


def test_extract_provider_rejects_unknown_provider():
    with pytest.raises(SystemExit):
        extract_provider(["--provider", "gemini"])


def test_apply_provider_switches_settings(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    get_settings.cache_clear()
    try:
        apply_provider("anthropic")
        assert get_settings().llm_provider == "anthropic"
    finally:
        get_settings.cache_clear()


def test_pin_agent_config_overrides_stored_openai_rows():
    AgentConfigCache.clear()
    try:
        AgentConfigCache.sync_from_cache(
            {
                "planner": AgentModelOverride(
                    provider="openai", model="gpt-5", temperature=0.2, max_tokens=900
                ),
                "reflection": AgentModelOverride(provider="openai", enabled=False),
            }
        )
        pin_agent_config_to_provider("anthropic")
        planner = AgentConfigCache.get("planner")
        assert planner == AgentModelOverride(provider="anthropic")
        assert AgentConfigCache.get("reflection").enabled is False
    finally:
        AgentConfigCache.clear()
