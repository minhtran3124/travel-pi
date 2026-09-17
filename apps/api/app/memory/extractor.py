"""Post-turn memory extraction from the last user—assistant exchange.

Pure function — unit-testable without a graph. The node wrapper in
``app.agents.nodes`` gates it behind ``allow_memory_write``, invokes it, and
upserts results to the store.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.prompts.registry import registry

logger = logging.getLogger(__name__)


@dataclass
class ExtractedMemories:
    """Typed result from ``extract_memories``; fields are always lists (empty on
    nothing found or parse failure)."""

    preferences: list[dict] = field(default_factory=list)
    instructions: list[dict] = field(default_factory=list)
    episodes: list[dict] = field(default_factory=list)


def _last_exchange(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Return the last user message through the end; falls back to the last 2
    messages when no user message is found."""
    user_idx: int | None = None
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            user_idx = i
            break
    if user_idx is None:
        return messages[-2:] if len(messages) >= 2 else messages
    return messages[user_idx:]


def _parse_content(raw: str) -> ExtractedMemories:
    """Defensive JSON parse → ``ExtractedMemories``. Never raises."""
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("memory_extraction: JSON parse failed")
        return ExtractedMemories()

    if not isinstance(obj, dict):
        return ExtractedMemories()

    prefs: list[dict] = []
    instrs: list[dict] = []
    episodes: list[dict] = []

    raw_prefs = obj.get("preferences")
    if isinstance(raw_prefs, list):
        for item in raw_prefs:
            if isinstance(item, dict) and "key" in item and "text" in item:
                prefs.append({"key": item["key"], "text": item["text"]})

    raw_instrs = obj.get("instructions")
    if isinstance(raw_instrs, list):
        for item in raw_instrs:
            if isinstance(item, dict) and "key" in item and "text" in item:
                instrs.append({"key": item["key"], "text": item["text"]})

    # A missing "episodes" key parses to an empty list, so older extractor output
    # (no episodes) stays backward-compatible.
    raw_episodes = obj.get("episodes")
    if isinstance(raw_episodes, list):
        for item in raw_episodes:
            if isinstance(item, dict) and "key" in item and "text" in item:
                ep = {
                    "key": item["key"],
                    "text": item["text"],
                    "city": item.get("city"),
                    "outcome": item.get("outcome", "proposed"),
                }
                episodes.append(ep)

    return ExtractedMemories(preferences=prefs, instructions=instrs, episodes=episodes)


def extract_memories(
    messages: list[BaseMessage], llm: BaseChatModel, *, callbacks: Any = None
) -> ExtractedMemories:
    """Extract durable preferences, standing instructions and trip episodes from a
    conversation.

    Sends the prompt and the last user—assistant exchange to *llm*, then
    defensively parses the JSON reply. Any error → empty ``ExtractedMemories``
    (best-effort, never raises).
    """
    prompt = registry.get("memory_extraction")
    exchange = _last_exchange(messages)
    msgs: list = [
        SystemMessage(content=prompt),
        HumanMessage(content=_serialize(exchange)),
    ]
    try:
        if callbacks is not None:
            raw = llm.invoke(msgs, config={"callbacks": callbacks}).content
        else:
            raw = llm.invoke(msgs).content
    except Exception:
        logger.exception("memory_extraction: LLM call failed")
        return ExtractedMemories()
    if not isinstance(raw, str):
        return ExtractedMemories()
    return _parse_content(raw)


def _serialize(messages: list[BaseMessage]) -> str:
    """Turn the exchange into a compact text block for the extractor prompt."""
    lines: list[str] = []
    for m in messages:
        role = m.__class__.__name__.replace("Message", "").lower()
        content = m.content
        if isinstance(content, str):
            lines.append(f"[{role}] {content}")
    return "\n".join(lines)
