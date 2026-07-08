"""Static catalog of LLM provider *profiles* for the agent layer.

A **profile** is a named endpoint the client can select (e.g. ``openai``,
``clinepass``, ``claude``). Each maps to:

* ``sdk`` — the LangChain ``init_chat_model(model_provider=...)`` value that
  actually talks to the API (``openai`` / ``anthropic`` / ``google_genai``).
* ``api_key_field`` — the ``Settings`` attribute holding this profile's own API
  key. Every profile has a dedicated one (no sharing across providers), so a
  gateway like ``clinepass`` needs its own ``clinepass_api_key``.
* ``base_url`` — an OpenAI-/Anthropic-compatible gateway host, or ``None`` to
  hit the provider's default endpoint. This is what lets ``clinepass`` run the
  ``openai`` SDK against the Cline gateway without any code change.
* ``models`` — the models available under the profile. A **reference list**
  for UIs/dropdowns, *not* an allowlist: the client does not reject an unlisted
  model.

The catalog is plain, editable reference data — add or trim profiles/models
freely. It has no dependencies (like ``constants``), so ``config``, the LLM
client, and repositories can all import it without a cycle. It is *not* seeded
into the DB — it is static app config, so it lives in ``core`` rather than
``app/data`` (which, by convention, is imported only by ``app/db/seed.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

# init_chat_model(model_provider=...) values — the real SDKs a profile runs on.
LLMSdk = Literal["openai", "anthropic", "google_genai"]


@dataclass(frozen=True)
class ProviderProfile:
    """A selectable provider endpoint: which SDK, which host, which models.

    ``api_key_field`` names the ``Settings`` attribute holding this profile's
    own API key — every catalog profile has a dedicated one (no sharing across
    providers). It is optional on the type only so ``clients.llm`` can build a
    bare fallback profile for an unlisted provider (which then carries no key).
    """

    sdk: LLMSdk
    base_url: str | None
    models: tuple[str, ...]
    api_key_field: str | None = None


def _profile(
    sdk: LLMSdk,
    models: list[str],
    *,
    base_url: str | None = None,
    api_key_field: str | None = None,
) -> ProviderProfile:
    return ProviderProfile(
        sdk=sdk,
        base_url=base_url,
        models=tuple(models),
        api_key_field=api_key_field,
    )


# The catalog. Native SDK profiles keep the names ``init_chat_model`` expects;
# gateway profiles (``clinepass`` / ``claude``) reuse an SDK against a custom
# ``base_url``.
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
        api_key_field="openai_api_key",
    ),
    "anthropic": _profile(
        "anthropic",
        [
            "claude-opus-4-8",
            "claude-sonnet-5",
            "claude-haiku-4-5-20251001",
        ],
        api_key_field="anthropic_api_key",
    ),
    "google_genai": _profile(
        "google_genai",
        [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
        ],
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
        api_key_field="clinepass_api_key",
    ),
    "claude": _profile(
        "anthropic",
        [
            "claude-opus-4-8",
            "claude-sonnet-5",
            "claude-haiku-4-5-20251001",
        ],
        base_url="https://api.claude.com/v1",
        api_key_field="claude_api_key",
    ),
}

# The set of valid profile names — the boundary allowlist used by callers that
# store/validate a provider (e.g. the agent_config repo).
PROVIDER_NAMES: frozenset[str] = frozenset(LLM_PROVIDERS)


def get_provider(name: str) -> ProviderProfile | None:
    """Return the profile for *name*, or ``None`` if it isn't in the catalog.

    :param name: The profile name to look up.
    :return: The matching :class:`ProviderProfile`, or ``None``.
    """
    return LLM_PROVIDERS.get(name)


# --- import-time consistency guard (typos fail loudly, like app/data/*) ------
_VALID_SDKS = set(get_args(LLMSdk))
for _name, _p in LLM_PROVIDERS.items():
    assert _p.sdk in _VALID_SDKS, f"{_name}: unknown sdk {_p.sdk!r}"
    assert _p.base_url is None or _p.base_url.startswith("http"), (
        f"{_name}: base_url must be an http(s) URL or None"
    )
    assert _p.models, f"{_name}: models list is empty"
    assert len(_p.models) == len(set(_p.models)), f"{_name}: duplicate models"
    assert _p.api_key_field, (
        f"{_name}: api_key_field required (each profile owns a key)"
    )

del _name, _p
