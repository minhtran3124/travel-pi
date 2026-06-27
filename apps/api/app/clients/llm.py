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

from app.core.config import get_settings

# Maps provider -> the settings field holding its API key.
_PROVIDER_KEY_FIELD = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "google_genai": "google_api_key",
}

# Graph nodes that default to the cheap ``fast_llm_model`` when a per-agent
# config omits ``model``. Everything else defaults to the main ``llm_model``.
# Kept here as the single source of truth for the tier mapping — the graph
# assembly imports it so injection and fallback never drift.
FAST_AGENTS = frozenset({"summarize", "journal", "budget", "reflection"})


def _build_chat_model(
    provider: str,
    model: str,
    *,
    temperature: float | None = None,
    **extra: Any,
) -> BaseChatModel:
    """Construct a chat model via ``init_chat_model``, injecting the provider's
    API key from settings when present. ``temperature`` and ``extra`` knobs are
    only forwarded when set, so reasoning models that reject ``temperature``
    keep working with the defaults."""
    s = get_settings()
    kwargs: dict[str, Any] = dict(extra)
    key = getattr(s, _PROVIDER_KEY_FIELD[provider], None)
    if key:
        kwargs["api_key"] = key
    if temperature is not None:
        kwargs["temperature"] = temperature
    return init_chat_model(model, model_provider=provider, streaming=True, **kwargs)


def get_llm(model: str | None = None, *, fast: bool = False) -> BaseChatModel:
    """Build a chat model for the configured provider.

    ``model`` overrides the configured model name; ``fast=True`` selects the
    cheaper ``fast_llm_model`` (used by sub-agents and summarisation). The API
    key is passed explicitly from settings when present so we never depend on
    process-wide env leakage; when absent the underlying client raises on first
    use, not here.
    """
    s = get_settings()
    name = model or (s.fast_llm_model if fast else s.llm_model)
    return _build_chat_model(s.llm_provider, name)


def get_fast_llm(model: str | None = None) -> BaseChatModel:
    """Build the cheap/fast chat model (sub-agents, summarisation, routing)."""
    return get_llm(model, fast=True)


def get_agent_llm(agent_name: str) -> BaseChatModel:
    """Build the chat model for a specific graph node.

    Resolves ``settings.agent_llm_configs[agent_name]`` with fallback: provider
    defaults to the global ``llm_provider``, model to the node's tier default
    (fast vs main), and any extra config key passes through to the model. A node
    with no override behaves exactly like ``get_llm()`` / ``get_fast_llm()``.
    """
    s = get_settings()
    fast = agent_name in FAST_AGENTS
    cfg = s.agent_llm_configs.get(agent_name)
    if cfg is None:
        return get_llm(fast=fast)
    provider = cfg.provider or s.llm_provider
    model = cfg.model or (s.fast_llm_model if fast else s.llm_model)
    return _build_chat_model(
        provider, model, temperature=cfg.temperature, **(cfg.model_extra or {})
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
