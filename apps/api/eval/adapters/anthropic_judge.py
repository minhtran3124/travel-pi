"""Anthropic-backed judge for DeepEval's G-Eval (``--judge-provider anthropic``).

``evalkit`` builds an OpenAI ``GPTModel`` by default; this adapter lets the same rubrics run on Claude
when OpenAI credit is not available. It is travel-pi wiring (it imports ``app``), so it lives in
``eval/`` and is handed to ``evalkit`` through ``set_judge_model_factory``.
"""

from __future__ import annotations

from typing import Any

from app.clients.llm import _build_chat_model, with_structured
from app.core.llm_providers import default_model_for
from deepeval.models import DeepEvalBaseLLM


class AnthropicJudgeModel(DeepEvalBaseLLM):
    """DeepEval judge model that calls Claude through the app's own chat-model builder."""

    def __init__(self, model: str | None = None, temperature: float = 0.0) -> None:
        self._temperature = temperature
        super().__init__(model or default_model_for("anthropic", fast=True))

    def load_model(self) -> Any:
        return _build_chat_model("anthropic", self.name, temperature=self._temperature)

    def generate(self, prompt: str, schema: Any = None) -> Any:
        """Plain text, or a *schema* instance when DeepEval asks for structured output."""
        if schema is not None:
            return with_structured(self.model, schema).invoke(prompt)
        return self.model.invoke(prompt).text

    async def a_generate(self, prompt: str, schema: Any = None) -> Any:
        if schema is not None:
            return await with_structured(self.model, schema).ainvoke(prompt)
        return (await self.model.ainvoke(prompt)).text

    def get_model_name(self) -> str:
        return f"anthropic/{self.name}"


def anthropic_judge_factory(
    judge_model: str, temperature: float
) -> AnthropicJudgeModel:
    """``evalkit`` hook: ignore the OpenAI default id, use the Claude judge model."""
    from eval.adapters.config import JUDGE_MODEL_ANTHROPIC

    return AnthropicJudgeModel(JUDGE_MODEL_ANTHROPIC, temperature)
