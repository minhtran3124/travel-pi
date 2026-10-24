"""Anthropic-shaped fake chat model.

Claude returns ``AIMessage.content`` as a list of ``thinking`` / ``text`` /
``tool_use`` blocks rather than a plain string. ``AnthropicShapedFakeLLM`` scripts
that shape so tests can prove a user sees the text, never the raw block list.
"""

from __future__ import annotations

from typing import Any

from app.clients.llm import FakeLLM
from langchain_core.messages import AIMessage, AIMessageChunk


def anthropic_blocks(text: str) -> list[dict[str, Any]]:
    """Content blocks as Claude returns them: an empty thinking block, then the text."""
    return [
        {"type": "thinking", "thinking": "", "signature": "x"},
        {"type": "text", "text": text},
    ]


def anthropic_message(text: str) -> AIMessage:
    return AIMessage(content=anthropic_blocks(text))


class AnthropicShapedFakeLLM(FakeLLM):
    """``FakeLLM`` whose string responses come back as Anthropic content blocks."""

    def _build_next(self) -> AIMessage:
        msg = super()._build_next()
        if isinstance(msg.content, str):
            return AIMessage(
                content=anthropic_blocks(msg.content), tool_calls=msg.tool_calls
            )
        return msg


def anthropic_chunk(text: str, *, index: int = 0) -> AIMessageChunk:
    return AIMessageChunk(content=[{"type": "text", "text": text, "index": index}])
