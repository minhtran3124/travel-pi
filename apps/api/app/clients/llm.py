"""Provider-agnostic LLM client: build chat models via ``init_chat_model``, no import side effects."""

from __future__ import annotations

import logging
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, PrivateAttr

from app.agents.constants import FAST_AGENTS
from app.core.agent_config_cache import AgentConfigCache
from app.core.config import get_settings
from app.core.llm_providers import ProviderProfile, default_model_for, get_provider

logger = logging.getLogger(__name__)


def _resolve_profile(provider: str) -> ProviderProfile:
    """Return the catalog profile for *provider*, or a bare fallback (the catalog is a reference list, not an allowlist)."""
    profile = get_provider(provider)
    if profile is not None:
        return profile
    return ProviderProfile(sdk=provider, base_url=None, models=())


def _is_openai_reasoning(model: str) -> bool:
    """True for OpenAI reasoning families (o-series, gpt-5*); others reject ``reasoning_effort``. Gateway-prefixed names (``openai/gpt-5.5``) count."""
    return model.rsplit("/", 1)[-1].startswith(("o1", "o3", "o4", "gpt-5"))


def _build_chat_model(
    provider: str,
    model: str,
    *,
    temperature: float | None = None,
    base_url: str | None = None,
    effort: str | None = None,
    **extra: Any,
) -> BaseChatModel:
    """Construct a chat model via ``init_chat_model``; ``temperature``/``extra`` forwarded only when set so reasoning models that reject them still work."""
    s = get_settings()
    profile = _resolve_profile(provider)
    kwargs: dict[str, Any] = dict(extra)

    # Each profile has its own dedicated key field — no sharing across providers.
    key = getattr(s, profile.api_key_field, None) if profile.api_key_field else None
    if key:
        kwargs["api_key"] = key

    # base_url precedence: explicit arg (per-agent) > profile gateway > global.
    resolved_base_url = base_url or profile.base_url or s.llm_base_url
    if resolved_base_url:
        kwargs["base_url"] = resolved_base_url

    if temperature is not None:
        if profile.supports_temperature:
            kwargs["temperature"] = temperature
        else:
            logger.debug(
                "[llm] provider %r rejects temperature; dropping %s",
                provider,
                temperature,
            )

    if effort is not None:
        if profile.sdk == "anthropic":
            kwargs["output_config"] = {
                **kwargs.get("output_config", {}),
                "effort": effort,
            }
        elif profile.sdk == "openai" and _is_openai_reasoning(model):
            # OpenAI tops out at "xhigh"; our "max" has no equivalent.
            kwargs["reasoning_effort"] = "xhigh" if effort == "max" else effort
        else:
            logger.debug("[llm] %s/%s ignores effort %s", provider, model, effort)

    if profile.default_max_tokens is not None:
        kwargs.setdefault("max_tokens", profile.default_max_tokens)

    kwargs.setdefault("max_retries", 0)  # graph owns retry; avoid SDK double-retry
    kwargs.setdefault(
        "timeout", s.llm_timeout_seconds
    )  # idle connect/read bound; langchain otherwise sends None

    if profile.sdk == "openai":
        # Without this, streaming OpenAI calls return no usage_metadata (SDK defaults stream_usage=False).
        kwargs["stream_usage"] = True

    return init_chat_model(model, model_provider=profile.sdk, streaming=True, **kwargs)


def _fallback_model(s: Any, provider: str, fast: bool) -> str | None:
    """Model when the DB row names none: env value if the provider is the global one, else that provider's own default."""
    if provider == s.llm_provider:
        env = s.fast_llm_model if fast else s.llm_model
        if env:
            return env
    return default_model_for(provider, fast=fast)


def get_llm(
    model: str | None = None,
    *,
    fast: bool = False,
    timeout: float | None = None,
) -> BaseChatModel:
    """Build a chat model for the configured provider; ``fast=True`` selects the cheaper ``fast_llm_model``; ``timeout`` overrides ``llm_timeout_seconds``."""
    s = get_settings()
    name = model or _fallback_model(s, s.llm_provider, fast)
    extra = {"timeout": timeout} if timeout is not None else {}
    return _build_chat_model(s.llm_provider, name, **extra)


def get_fast_llm(model: str | None = None) -> BaseChatModel:
    """Build the cheap/fast chat model (sub-agents, summarisation, routing)."""
    return get_llm(model, fast=True)


def get_agent_llm(
    agent_name: str,
    *,
    timeout: float | None = None,
) -> BaseChatModel:
    """Build the chat model for a graph node, per-field from the DB override with global defaults as fallback; no DB row behaves like ``get_llm()``."""
    s = get_settings()
    fast = agent_name in FAST_AGENTS

    db = AgentConfigCache.get(agent_name)
    if db is None:
        return get_llm(fast=fast, timeout=timeout)

    provider = db.provider or s.llm_provider
    model = db.model or _fallback_model(s, provider, fast)
    extra = {"max_tokens": db.max_tokens} if db.max_tokens is not None else {}
    if timeout is not None:
        extra["timeout"] = timeout

    return _build_chat_model(
        provider,
        model,
        temperature=db.temperature,
        base_url=db.base_url,
        effort=db.effort,
        **extra,
    )


def _all_required_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """JSON schema for *schema* with every property listed as ``required`` (nullable ones stay nullable).

    Anthropic's native structured output rejects a schema with too many OPTIONAL properties
    (400 ``Schema is too complex``; ``SupervisorIntent`` trips it with 14). Marking them all
    required keeps the same shape: a field that was ``X | None`` still accepts ``null``.
    """
    from anthropic import transform_schema

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    out = transform_schema(schema.model_json_schema())
    walk(out)
    return out


def with_structured(llm: Any, schema: Any) -> Runnable:
    """Bind *schema* as structured output, picking the method the model's provider accepts.

    Anthropic rejects the forced ``tool_choice`` that ``method="function_calling"`` sends
    (400 on Claude Opus/Sonnet 5.5), so it gets native ``json_schema`` output, with every
    property marked required to stay under its optional-property limit (see
    :func:`_all_required_schema`). Every other provider keeps ``function_calling``, which
    avoids OpenAI's benign ``ParsedChatCompletion.parsed`` serializer warning on the native
    json_schema parse path.
    """
    try:
        params = llm._get_ls_params()
    except (AttributeError, TypeError, NotImplementedError):
        params = None
    provider = params.get("ls_provider") if isinstance(params, dict) else None
    if provider != "anthropic":
        return llm.with_structured_output(schema, method="function_calling")
    if not (isinstance(schema, type) and issubclass(schema, BaseModel)):
        return llm.with_structured_output(schema, method="json_schema")
    # bind() replaces the model's own output_config wholesale, so carry its effort over.
    base_config = getattr(llm, "output_config", None) or {}
    bound = llm.bind(
        output_config={
            **base_config,
            "format": {"type": "json_schema", "schema": _all_required_schema(schema)},
        }
    )
    return bound | PydanticOutputParser(pydantic_object=schema)


class FakeLLM(BaseChatModel):
    """Deterministic chat model for tests — cycles scripted ``responses``/``structured_responses``, zero network."""

    responses: list[Any] = []
    structured_responses: list[Any] = []
    _cursor: int = PrivateAttr(default=0)
    _structured_cursor: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "fake-llm"

    def _next(self) -> AIMessage:
        msg = self._build_next()
        # Deterministic usage so offline turns exercise the token/cost/latency metrics path.
        if not msg.usage_metadata:
            msg.usage_metadata = {
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
            }
            msg.response_metadata = {**msg.response_metadata, "model_name": "fake-llm"}
        return msg

    def _build_next(self) -> AIMessage:
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
