"""Provider-agnostic LLM client (specs/travel-agent Task 1.1).

The agent layer never imports a provider SDK directly: it builds chat models via
LangChain's ``init_chat_model()``, so switching provider is a settings change
(``LLM_PROVIDER``), not a code change. Importing this module has **no** side
effects — no network, no key validation — construction happens only when
``get_llm()`` / ``get_fast_llm()`` is called.

``FakeLLM`` is the deterministic stand-in used throughout the test suite: it
scripts ``AIMessage`` responses (including tool calls) and supports
``bind_tools`` / ``with_structured_output`` so it can drive the full agent graph
without any API key or network access.
"""

from __future__ import annotations

from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import PrivateAttr

from app.agents.constants import FAST_AGENTS
from app.core.agent_config_cache import AgentConfigCache
from app.core.config import get_settings
from app.core.llm_providers import ProviderProfile, get_provider

# The settings field holding each SDK's API key. A profile's key comes from its
# own ``api_key_field`` when set (a dedicated gateway token), else it falls back
# to the SDK's shared key here — so an existing openai/anthropic key keeps a
# gateway profile working.
_SDK_KEY_FIELD = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "google_genai": "google_api_key",
}


def _resolve_api_key(settings: Any, profile: ProviderProfile) -> str | None:
    """Return the API key for *profile*: its dedicated field first, then the
    SDK's shared key. Skips fields that are unset/empty.

    :param settings: The application settings object.
    :param profile: The provider profile being built.
    :return: The resolved API key, or ``None`` when none is configured.
    """
    for field in (profile.api_key_field, _SDK_KEY_FIELD.get(profile.sdk)):
        if field:
            key = getattr(settings, field, None)
            if key:
                return key
    return None


def _resolve_profile(provider: str) -> ProviderProfile:
    """Return the catalog profile for *provider*.

    Falls back to a bare profile that treats the name as its own SDK with no
    gateway, so any provider string stays usable — the catalog is a reference
    list, not an allowlist.

    :param provider: The profile name (or raw SDK name) to resolve.
    :return: The matching :class:`ProviderProfile`, or a bare fallback.
    """
    profile = get_provider(provider)
    if profile is not None:
        return profile
    return ProviderProfile(name=provider, sdk=provider, base_url=None, models=())


def _build_chat_model(
    provider: str,
    model: str,
    *,
    temperature: float | None = None,
    base_url: str | None = None,
    **extra: Any,
) -> BaseChatModel:
    """Construct a chat model via ``init_chat_model`` for a provider *profile*.

    The profile decides the underlying SDK (``model_provider``), whether a
    gateway ``base_url`` is needed, and which settings key to inject.
    ``temperature`` and ``extra`` knobs are only forwarded when set, so
    reasoning models that reject ``temperature`` keep working with the defaults.

    :param provider: The provider profile name (e.g. ``openai``, ``clinepass``).
    :param model: The model to use.
    :param temperature: The temperature to use, when supported.
    :param base_url: Per-call override; wins over the profile's gateway and the
        global ``settings.llm_base_url`` fallback.
    :param extra: Extra arguments to pass to the chat model.
    :return: A chat model.
    """
    s = get_settings()
    profile = _resolve_profile(provider)
    kwargs: dict[str, Any] = dict(extra)

    key = _resolve_api_key(s, profile)
    if key:
        kwargs["api_key"] = key

    # base_url precedence: explicit arg (per-agent) > profile gateway > global.
    resolved_base_url = base_url or profile.base_url or s.llm_base_url
    if resolved_base_url:
        kwargs["base_url"] = resolved_base_url

    if temperature is not None:
        kwargs["temperature"] = temperature

    return init_chat_model(model, model_provider=profile.sdk, streaming=True, **kwargs)


def get_llm(model: str | None = None, *, fast: bool = False) -> BaseChatModel:
    """Build a chat model for the configured provider.

    ``model`` overrides the configured model name; ``fast=True`` selects the
    cheaper ``fast_llm_model`` (used by sub-agents and summarisation). The API
    key is passed explicitly from settings when present so we never depend on
    process-wide env leakage; when absent the underlying client raises on first
    use, not here.

    :param model: Overrides the configured model name.
    :param fast: When ``True``, selects the cheaper ``fast_llm_model``.
    :return: A chat model.
    """
    s = get_settings()
    name = model or (s.fast_llm_model if fast else s.llm_model)
    return _build_chat_model(s.llm_provider, name)


def get_fast_llm(model: str | None = None) -> BaseChatModel:
    """Build the cheap/fast chat model (sub-agents, summarisation, routing).

    :param model: Overrides the configured fast model name.
    :return: A chat model.
    """
    return get_llm(model, fast=True)


def _coalesce(*values: Any) -> Any:
    """Return the first non-``None`` value, or ``None`` if all are ``None``."""
    return next((v for v in values if v is not None), None)


def get_agent_llm(agent_name: str) -> BaseChatModel:
    """Build the chat model for a specific graph node.

    Resolves per field with a **DB → env → global default** fallback: the
    DB-backed override (``AgentConfigCache``), then
    ``settings.agent_llm_configs[agent_name]``, then the global default. Model
    falls back to the node's tier default (fast vs main, via ``FAST_AGENTS``)
    when nothing overrides it. The chosen ``provider`` profile supplies its own
    gateway ``base_url`` inside ``_build_chat_model``; only a per-agent
    ``base_url`` override is threaded here. A node with no override behaves
    exactly like ``get_llm()`` / ``get_fast_llm()``.

    :param agent_name: The graph node name to resolve config for.
    :return: A chat model.
    """
    s = get_settings()
    fast = agent_name in FAST_AGENTS

    env = s.agent_llm_configs.get(agent_name)
    db = AgentConfigCache.get(agent_name)

    if env is None and db is None:
        return get_llm(fast=fast)

    provider = _coalesce(
        db.provider if db else None,
        env.provider if env else None,
        s.llm_provider,
    )
    model = _coalesce(
        db.model if db else None,
        env.model if env else None,
        s.fast_llm_model if fast else s.llm_model,
    )

    return _build_chat_model(
        provider,
        model,
        temperature=env.temperature if env else None,
        base_url=db.base_url if db else None,
        **((env.model_extra if env else None) or {}),
    )


class FakeLLM(BaseChatModel):
    """Deterministic chat model for tests — scripts responses, zero network.

    - ``responses``: cycled through by ``invoke``/``_generate``. Items may be a
      plain ``str`` (becomes ``AIMessage(content=...)``), an ``AIMessage`` (use
      as-is, e.g. carrying ``tool_calls``), or a ``dict`` with ``content`` /
      ``tool_calls`` keys.
    - ``structured_responses``: cycled through by the runnable returned from
      ``with_structured_output`` — items are returned verbatim (already schema
      instances) so callers get the object they expect.
    """

    responses: list[Any] = []
    structured_responses: list[Any] = []
    _cursor: int = PrivateAttr(default=0)
    _structured_cursor: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "fake-llm"

    def _next(self) -> AIMessage:
        if not self.responses:
            return AIMessage(content="")
        item = self.responses[self._cursor % len(self.responses)]
        self._cursor += 1
        if isinstance(item, AIMessage):
            return item
        if isinstance(item, str):
            return AIMessage(content=item)
        if isinstance(item, dict):
            return AIMessage(
                content=item.get("content", ""),
                tool_calls=item.get("tool_calls", []),
            )
        raise TypeError(f"Unsupported FakeLLM response item: {type(item)!r}")

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._next())])

    def bind_tools(self, tools: Any, **kwargs: Any) -> BaseChatModel:
        """No-op: scripted ``tool_calls`` in ``responses`` drive tool execution."""
        return self

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable:
        """Return a runnable yielding the next ``structured_responses`` item."""

        def _call(_messages: Any) -> Any:
            if not self.structured_responses:
                raise ValueError("FakeLLM.structured_responses is empty")
            item = self.structured_responses[
                self._structured_cursor % len(self.structured_responses)
            ]
            self._structured_cursor += 1
            return item

        return RunnableLambda(_call)
