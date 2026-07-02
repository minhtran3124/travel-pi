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
    # config's default provider + the env AGENT_LLM_CONFIGS path use SDK names
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
    assert p.base_url == "https://api.claude.com/v1"
    assert p.api_key_field == "claude_api_key"


def test_native_profiles_have_no_dedicated_key_field():
    for sdk in _VALID_SDKS:
        assert LLM_PROVIDERS[sdk].api_key_field is None


def test_get_provider_unknown_returns_none():
    assert get_provider("does-not-exist") is None


def test_provider_names_matches_catalog_keys():
    assert frozenset(LLM_PROVIDERS) == PROVIDER_NAMES
    assert {"openai", "clinepass", "claude"} <= PROVIDER_NAMES


def test_every_profile_satisfies_the_guard_invariants():
    for name, p in LLM_PROVIDERS.items():
        assert p.name == name
        assert p.sdk in _VALID_SDKS
        assert p.base_url is None or p.base_url.startswith("http")
        assert p.models, f"{name}: empty models"
        assert len(p.models) == len(set(p.models)), f"{name}: duplicate models"
