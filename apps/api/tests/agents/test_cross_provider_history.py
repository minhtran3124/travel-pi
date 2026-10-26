"""A thread mixing Claude and OpenAI turns must not replay one provider's reasoning blocks to the other (#257)."""

from __future__ import annotations

from typing import Any

from app.agents.state import provider_of, strip_foreign_reasoning
from app.agents.subagents._base import build_subagent
from app.clients.llm import FakeLLM
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def _claude_turn() -> AIMessage:
    return AIMessage(
        content=[
            {"type": "thinking", "thinking": "plan", "signature": "sig"},
            {"type": "redacted_thinking", "data": "xx"},
            {"type": "text", "text": "Checking."},
            {"type": "tool_use", "id": "t1", "name": "w", "input": {}},
        ],
        tool_calls=[{"name": "w", "args": {}, "id": "t1", "type": "tool_call"}],
        response_metadata={"model_provider": "anthropic"},
    )


def _openai_turn() -> AIMessage:
    return AIMessage(
        content=[
            {"type": "reasoning", "id": "rs_1", "summary": []},
            {"type": "text", "text": "Sure."},
        ],
        response_metadata={"model_provider": "openai"},
    )


def _types(msg: AIMessage) -> list[str]:
    return [b["type"] for b in msg.content]


def test_cross_provider_claude_reasoning_stripped_for_openai():
    claude = _claude_turn()
    out = strip_foreign_reasoning([HumanMessage("hi"), claude], "openai")
    assert _types(out[1]) == ["text", "tool_use"]
    assert out[1].tool_calls == claude.tool_calls
    # State is untouched: the original message keeps its thinking blocks.
    assert _types(claude)[:2] == ["thinking", "redacted_thinking"]


def test_cross_provider_openai_reasoning_stripped_for_claude():
    out = strip_foreign_reasoning([_openai_turn()], "anthropic")
    assert _types(out[0]) == ["text"]


def test_cross_provider_same_provider_untouched():
    msgs = [_claude_turn(), _openai_turn()]
    assert _types(strip_foreign_reasoning(msgs, "anthropic")[0])[0] == "thinking"
    assert _types(strip_foreign_reasoning(msgs, "openai")[1])[0] == "reasoning"


def test_cross_provider_untagged_or_unknown_provider_untouched():
    untagged = AIMessage(content=[{"type": "thinking", "thinking": "x"}])
    msgs = [untagged, ToolMessage(content="ok", tool_call_id="t1"), _claude_turn()]
    assert strip_foreign_reasoning(msgs, "openai")[0] is untagged
    assert strip_foreign_reasoning(msgs, None) is msgs


def test_cross_provider_string_content_untouched():
    plain = AIMessage(content="hello", response_metadata={"model_provider": "openai"})
    assert strip_foreign_reasoning([plain], "anthropic")[0] is plain


class _OpenAIShapedFake(FakeLLM):
    """FakeLLM that reports an OpenAI provider and records what it was sent."""

    seen: list[Any] = []

    def _get_ls_params(self, *args: Any, **kwargs: Any) -> dict:
        return {"ls_provider": "openai"}

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen.append(list(messages))
        return super()._generate(messages, stop, run_manager, **kwargs)


def test_cross_provider_specialist_strips_before_model_call():
    assert provider_of(object()) is None
    llm = _OpenAIShapedFake(responses=["done"], seen=[])
    agent = build_subagent("planner", [], lambda _=None: llm, "p")
    agent.invoke({"messages": [HumanMessage("hi"), _claude_turn()]})
    sent = [m for m in llm.seen[0] if isinstance(m, AIMessage)]
    assert [_types(m) for m in sent] == [["text", "tool_use"]]
