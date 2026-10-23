"""Static catalog of selectable LLM provider *profiles* (SDK, gateway base_url, API-key field, reference model list) for the agent layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

# init_chat_model(model_provider=...) values — the real SDKs a profile runs on.
LLMSdk = Literal["openai", "anthropic", "google_genai"]


@dataclass(frozen=True)
class ProviderProfile:
    """A selectable provider endpoint: which SDK, which gateway host, which models."""

    sdk: LLMSdk
    base_url: str | None
    models: tuple[str, ...]
    api_key_field: str | None = None
    # Anthropic rejects ``temperature`` on current Claude models.
    supports_temperature: bool = True
    # Fallback output cap when the DB row sets none (langchain-anthropic otherwise defaults Haiku to 4096).
    default_max_tokens: int | None = None
    # Models used when neither the DB row nor LLM_MODEL/FAST_LLM_MODEL names one.
    default_model: str | None = None
    default_fast_model: str | None = None


def _profile(
    sdk: LLMSdk,
    models: list[str],
    *,
    base_url: str | None = None,
    api_key_field: str | None = None,
    supports_temperature: bool = True,
    default_max_tokens: int | None = None,
    default_model: str | None = None,
    default_fast_model: str | None = None,
) -> ProviderProfile:
    return ProviderProfile(
        sdk=sdk,
        base_url=base_url,
        models=tuple(models),
        api_key_field=api_key_field,
        supports_temperature=supports_temperature,
        default_max_tokens=default_max_tokens,
        default_model=default_model,
        default_fast_model=default_fast_model,
    )


# Native SDK profiles keep the names init_chat_model expects; gateway profiles reuse an SDK against a custom base_url.
LLM_PROVIDERS: dict[str, ProviderProfile] = {
    "openai": _profile(
        "openai",
        [
            "gpt-4o-mini",
            "gpt-4.1-mini",
            "gpt-5.5",
            "gpt-5.4-mini",
            "gpt-5.4-nano",
        ],
        default_model="gpt-5",
        default_fast_model="gpt-5-mini",
        api_key_field="openai_api_key",
    ),
    "anthropic": _profile(
        "anthropic",
        [
            "claude-opus-5-5",
            "claude-sonnet-5-5",
            "claude-haiku-5-5",
            "claude-opus-4-8",
            "claude-sonnet-5",
            "claude-haiku-4-5-20251001",
        ],
        supports_temperature=False,
        default_max_tokens=16000,
        default_model="claude-sonnet-5-5",
        default_fast_model="claude-haiku-5-5",
        api_key_field="anthropic_api_key",
    ),
    "google_genai": _profile(
        "google_genai",
        [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
        ],
        default_model="gemini-2.5-pro",
        default_fast_model="gemini-2.5-flash",
        api_key_field="google_api_key",
    ),
    "clinepass": _profile(
        "openai",
        [
            "openai/gpt-4o-mini",
            "openai/gpt-4.1-mini",
            "openai/gpt-5.5",
            "openai/gpt-5.4-mini",
            "openai/gpt-5.4-nano",
        ],
        base_url="https://api.cline.bot/api/v1",
        default_model="openai/gpt-5.5",
        default_fast_model="openai/gpt-5.4-mini",
        api_key_field="clinepass_api_key",
    ),
    "claude": _profile(
        "anthropic",
        [
            "claude-opus-5-5",
            "claude-sonnet-5-5",
            "claude-haiku-5-5",
            "claude-opus-4-8",
            "claude-sonnet-5",
            "claude-haiku-4-5-20251001",
        ],
        # No /v1: the Anthropic SDK appends /v1/messages itself.
        base_url="https://api.claude.com",
        supports_temperature=False,
        default_max_tokens=16000,
        default_model="claude-sonnet-5-5",
        default_fast_model="claude-haiku-5-5",
        api_key_field="claude_api_key",
    ),
}

# Valid profile names — the allowlist callers validate a stored provider against.
PROVIDER_NAMES: frozenset[str] = frozenset(LLM_PROVIDERS)


def get_provider(name: str) -> ProviderProfile | None:
    """Return the profile for *name*, or ``None`` if it isn't in the catalog."""
    return LLM_PROVIDERS.get(name)


def default_model_for(provider: str, *, fast: bool = False) -> str | None:
    """Return the catalog default model for *provider* (tier by ``fast``); ``None`` for an unknown profile."""
    profile = LLM_PROVIDERS.get(provider)
    if profile is None:
        return None
    return profile.default_fast_model if fast else profile.default_model


# Import-time consistency guard: typos fail loudly.
_VALID_SDKS = set(get_args(LLMSdk))
for _name, _p in LLM_PROVIDERS.items():
    assert _p.sdk in _VALID_SDKS, f"{_name}: unknown sdk {_p.sdk!r}"
    assert _p.base_url is None or _p.base_url.startswith("http"), (
        f"{_name}: base_url must be an http(s) URL or None"
    )
    assert _p.models, f"{_name}: models list is empty"
    assert len(_p.models) == len(set(_p.models)), f"{_name}: duplicate models"
    assert _p.default_model and _p.default_fast_model, (
        f"{_name}: default_model and default_fast_model required"
    )
    assert _p.api_key_field, (
        f"{_name}: api_key_field required (each profile owns a key)"
    )

del _name, _p
