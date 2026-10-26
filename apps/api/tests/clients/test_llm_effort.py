"""Per-agent ``effort`` knob: Anthropic ``output_config`` / OpenAI ``reasoning_effort``."""

import pytest
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel


def _capture_init(monkeypatch):
    captured: dict = {}

    def fake_init(model, **kwargs):
        captured["model"] = model
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("app.clients.llm.init_chat_model", fake_init)
    return captured


def test_anthropic_effort_becomes_output_config(monkeypatch):
    captured = _capture_init(monkeypatch)
    from app.clients.llm import _build_chat_model

    _build_chat_model("anthropic", "claude-opus-5-5", effort="low")
    assert captured["kwargs"]["output_config"] == {"effort": "low"}


def test_effort_omitted_when_unset(monkeypatch):
    captured = _capture_init(monkeypatch)
    from app.clients.llm import _build_chat_model

    _build_chat_model("anthropic", "claude-opus-5-5")
    assert "output_config" not in captured["kwargs"]
    _build_chat_model("openai", "gpt-5")
    assert "reasoning_effort" not in captured["kwargs"]


@pytest.mark.parametrize(
    ("model", "effort", "expected"),
    [("gpt-5", "high", "high"), ("openai/gpt-5.5", "max", "xhigh")],
)
def test_openai_reasoning_model_maps_effort(monkeypatch, model, effort, expected):
    captured = _capture_init(monkeypatch)
    from app.clients.llm import _build_chat_model

    _build_chat_model("openai", model, effort=effort)
    assert captured["kwargs"]["reasoning_effort"] == expected


def test_openai_non_reasoning_model_ignores_effort(monkeypatch):
    captured = _capture_init(monkeypatch)
    from app.clients.llm import _build_chat_model

    _build_chat_model("openai", "gpt-4o-mini", effort="high")
    assert "reasoning_effort" not in captured["kwargs"]


def test_get_agent_llm_passes_db_effort(monkeypatch):
    from app.core.agent_config_cache import AgentConfigCache, AgentModelOverride

    seen: dict = {}

    def fake(provider, model, **kw):
        seen.update(kw)
        return object()

    monkeypatch.setattr("app.clients.llm._build_chat_model", fake)
    AgentConfigCache.clear()
    AgentConfigCache.sync_from_cache(
        {"planner": AgentModelOverride(provider="anthropic", effort="medium")}
    )
    try:
        from app.clients.llm import get_agent_llm

        get_agent_llm("planner")
    finally:
        AgentConfigCache.clear()
    assert seen["effort"] == "medium"


def test_structured_output_keeps_model_effort():
    from app.clients.llm import with_structured

    class _S(BaseModel):
        a: str

    class _Stub:
        output_config = {"effort": "low"}

        def _get_ls_params(self):
            return {"ls_provider": "anthropic"}

        def bind(self, **kw):
            self.bound = kw
            return RunnableLambda(lambda x: x)

    stub = _Stub()
    with_structured(stub, _S)
    assert stub.bound["output_config"]["effort"] == "low"
    assert "format" in stub.bound["output_config"]
