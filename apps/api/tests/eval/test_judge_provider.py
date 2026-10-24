"""``--judge-provider anthropic``: the judge and extractor run on Claude, offline (no network)."""

from __future__ import annotations

import pytest
from app.core.config import get_settings
from eval import __main__ as eval_main
from eval.adapters.anthropic_judge import AnthropicJudgeModel, anthropic_judge_factory
from eval.provider import extract_judge_provider
from evalkit.metrics import judged
from pydantic import BaseModel


def test_extract_judge_provider_flag_env_and_default(monkeypatch):
    monkeypatch.delenv("EVAL_JUDGE_PROVIDER", raising=False)
    assert extract_judge_provider(["--suite", "smoke"]) == (
        "openai",
        ["--suite", "smoke"],
    )
    assert extract_judge_provider(["--judge-provider", "anthropic", "--dry-run"]) == (
        "anthropic",
        ["--dry-run"],
    )
    assert extract_judge_provider(["--judge-provider=anthropic"]) == ("anthropic", [])
    monkeypatch.setenv("EVAL_JUDGE_PROVIDER", "anthropic")
    assert extract_judge_provider([]) == ("anthropic", [])


def test_extract_judge_provider_rejects_unknown():
    with pytest.raises(SystemExit):
        extract_judge_provider(["--judge-provider", "gemini"])


def test_judge_available_checks_the_judge_providers_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "real-looking-key")
    assert eval_main._judge_available("openai") is False
    assert eval_main._judge_available("anthropic") is True
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    assert eval_main._judge_available("anthropic") is False


def test_build_geval_uses_the_factory_when_set(monkeypatch):
    seen = {}

    def factory(model, temperature):
        seen["args"] = (model, temperature)
        return object.__new__(AnthropicJudgeModel)

    captured = {}
    monkeypatch.setattr(judged, "GEval", lambda **kw: captured.update(kw) or kw)
    judged.set_judge_model_factory(factory)
    try:
        judged.build_geval(
            "answer_relevancy", {"criteria": "c", "evaluation_params": []}
        )
    finally:
        judged.set_judge_model_factory(None)
    assert seen["args"] == (judged.DEFAULT_JUDGE_MODEL, judged.DEFAULT_TEMPERATURE)
    assert isinstance(captured["model"], AnthropicJudgeModel)


class _Verdict(BaseModel):
    score: int


class _FakeChat:
    def __init__(self):
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)

        class _Msg:
            text = "plain"

        return _Msg()


def test_anthropic_judge_model_generates_text_and_structured(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    get_settings.cache_clear()
    built = {}

    def fake_build(provider, model, **kw):
        built.update(provider=provider, model=model, **kw)
        return _FakeChat()

    monkeypatch.setattr("eval.adapters.anthropic_judge._build_chat_model", fake_build)
    monkeypatch.setattr(
        "eval.adapters.anthropic_judge.with_structured",
        lambda llm, schema: type(
            "R", (), {"invoke": lambda self, p: schema(score=7)}
        )(),
    )
    model = anthropic_judge_factory("gpt-4o-mini", 0.0)
    assert built["provider"] == "anthropic" and built["model"].startswith("claude-")
    assert built["temperature"] == 0.0
    assert model.generate("hi") == "plain"
    assert model.generate("hi", schema=_Verdict) == _Verdict(score=7)
    assert model.get_model_name().startswith("anthropic/claude-")
