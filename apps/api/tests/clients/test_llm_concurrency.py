"""Per-process LLM semaphore, graph-level 429 retry, and per-turn max_concurrency."""

import asyncio
from typing import Any

import pytest
from app.agents.retry import LLM_RETRY
from app.clients.llm import _build_chat_model
from app.clients.llm_limiter import LLMConcurrencyLimiter, reset_limiter
from app.core.config import get_settings
from app.routers.agent import _config
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.graph import END, START, MessagesState, StateGraph

LIMIT = 6


class CountingLLM(BaseChatModel):
    """FakeLLM-style model that records peak in-flight calls and can raise 429s."""

    inflight: int = 0
    peak: int = 0
    fail_429: int = 0

    @property
    def _llm_type(self) -> str:
        return "counting"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        raise NotImplementedError

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        self.inflight += 1
        self.peak = max(self.peak, self.inflight)
        try:
            await asyncio.sleep(0.02)
            if self.fail_429 > 0:
                self.fail_429 -= 1
                err = RuntimeError("rate limited")
                err.status_code = 429  # type: ignore[attr-defined]
                raise err
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content="ok"))]
            )
        finally:
            self.inflight -= 1


@pytest.fixture(autouse=True)
def _fresh_limiter():
    reset_limiter()
    yield
    reset_limiter()


def test_ten_concurrent_calls_never_exceed_limit():
    asyncio.run(_test_ten_concurrent_calls_never_exceed_limit())


async def _test_ten_concurrent_calls_never_exceed_limit():
    llm = CountingLLM(callbacks=[LLMConcurrencyLimiter(LIMIT)])
    await asyncio.gather(*(llm.ainvoke("hi") for _ in range(10)))
    assert 1 < llm.peak <= LIMIT


def test_slot_released_on_error():
    asyncio.run(_test_slot_released_on_error())


async def _test_slot_released_on_error():
    llm = CountingLLM(callbacks=[LLMConcurrencyLimiter(1)], fail_429=3)
    for _ in range(3):
        with pytest.raises(RuntimeError):
            await llm.ainvoke("hi")
    assert (await llm.ainvoke("hi")).content == "ok"  # would hang if a slot leaked


def test_simulated_429_is_retried_by_graph_policy():
    asyncio.run(_test_simulated_429_is_retried_by_graph_policy())


async def _test_simulated_429_is_retried_by_graph_policy():
    llm = CountingLLM(callbacks=[LLMConcurrencyLimiter(LIMIT)], fail_429=2)

    async def assistant(state: MessagesState) -> dict[str, Any]:
        return {"messages": [await llm.ainvoke(state["messages"])]}

    g = StateGraph(MessagesState)
    g.add_node("assistant", assistant, retry_policy=LLM_RETRY)
    g.add_edge(START, "assistant")
    g.add_edge("assistant", END)
    out = await g.compile().ainvoke({"messages": [("user", "hi")]})
    assert out["messages"][-1].content == "ok"
    assert llm.fail_429 == 0


def test_build_chat_model_attaches_limiter(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_GLOBAL_CONCURRENCY", "6")
    get_settings.cache_clear()
    try:
        model = _build_chat_model("openai", "gpt-4o-mini")
        assert any(isinstance(c, LLMConcurrencyLimiter) for c in model.callbacks)
        monkeypatch.setenv("LLM_GLOBAL_CONCURRENCY", "0")
        get_settings.cache_clear()
        model = _build_chat_model("openai", "gpt-4o-mini")
        assert not model.callbacks
    finally:
        get_settings.cache_clear()


def test_config_max_concurrency(monkeypatch):
    run_id = "00000000-0000-0000-0000-000000000001"
    monkeypatch.delenv("AGENT_MAX_CONCURRENCY", raising=False)
    get_settings.cache_clear()
    try:
        assert "max_concurrency" not in _config(
            "t", "u", None, run_id=run_id, metrics=object()
        )
        monkeypatch.setenv("AGENT_MAX_CONCURRENCY", "3")
        get_settings.cache_clear()
        cfg = _config("t", "u", None, run_id=run_id, metrics=object())
        assert cfg["max_concurrency"] == 3
    finally:
        get_settings.cache_clear()
