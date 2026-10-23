"""LLM provider profile catalog (app/core/llm_providers.py).

Pins the catalog shape and the invariants the import-time guard enforces, plus
the two behaviours the client relies on: gateway profiles carry a base_url and
map onto a real SDK; native SDK names are present so config/env keep resolving.
"""

from app.core.llm_providers import (
    LLM_PROVIDERS,
    PROVIDER_NAMES,
    ProviderProfile,
    get_provider,
)

# The SDK names init_chat_model accepts — every profile must map onto one.
_VALID_SDKS = {"openai", "anthropic", "google_genai"}


def test_native_sdk_profiles_present():
    # The global LLM_PROVIDER default + DB agent_config rows may use SDK names
    # directly, so those must exist as catalog keys.
    for sdk in _VALID_SDKS:
        assert sdk in LLM_PROVIDERS
        assert LLM_PROVIDERS[sdk].sdk == sdk
        assert LLM_PROVIDERS[sdk].base_url is None


def test_clinepass_is_openai_sdk_behind_a_gateway():
    p = get_provider("clinepass")
    assert isinstance(p, ProviderProfile)
    assert p.sdk == "openai"  # runs the OpenAI SDK...
    assert p.base_url == "https://api.cline.bot/api/v1"  # ...against the gateway
    assert p.api_key_field == "clinepass_api_key"  # with its own token
    assert p.models  # reference list, non-empty


def test_claude_profile_uses_anthropic_sdk_and_gateway():
    p = get_provider("claude")
    assert p is not None
    assert p.sdk == "anthropic"
    assert p.base_url == "https://api.claude.com"  # SDK appends /v1/messages
    assert p.api_key_field == "claude_api_key"


def test_every_profile_has_its_own_key_field():
    # No sharing: each profile names a distinct settings key field.
    fields = [p.api_key_field for p in LLM_PROVIDERS.values()]
    assert all(fields)  # every profile has one
    assert len(fields) == len(set(fields))  # and they are all distinct
    assert LLM_PROVIDERS["openai"].api_key_field == "openai_api_key"
    assert LLM_PROVIDERS["clinepass"].api_key_field == "clinepass_api_key"


def test_get_provider_unknown_returns_none():
    assert get_provider("does-not-exist") is None


def test_provider_names_matches_catalog_keys():
    assert frozenset(LLM_PROVIDERS) == PROVIDER_NAMES
    assert {"openai", "clinepass", "claude"} <= PROVIDER_NAMES


def test_every_profile_satisfies_the_guard_invariants():
    for name, p in LLM_PROVIDERS.items():
        assert p.sdk in _VALID_SDKS
        assert p.base_url is None or p.base_url.startswith("http")
        assert p.models, f"{name}: empty models"
        assert len(p.models) == len(set(p.models)), f"{name}: duplicate models"
        assert p.api_key_field, f"{name}: missing api_key_field"


def test_anthropic_profiles_drop_temperature_and_cap_tokens():
    for name in ("anthropic", "claude"):
        p = get_provider(name)
        assert p is not None
        assert p.supports_temperature is False
        assert p.default_max_tokens == 16000
        assert p.default_model == "claude-sonnet-5-5"
        assert p.default_fast_model == "claude-haiku-5-5"
        assert "claude-sonnet-5-5" in p.models
        assert "claude-sonnet-5" in p.models  # legacy rows still selectable


def test_openai_keeps_temperature():
    p = get_provider("openai")
    assert p is not None
    assert p.supports_temperature is True
    assert p.default_max_tokens is None
