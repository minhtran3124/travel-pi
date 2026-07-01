"""Conversation summarisation (specs/travel-agent Task 2.2).

Long agent threads bloat the checkpoint and overflow the context window. When
the message count crosses ``summarize_threshold``, the graph compresses the
older turns into a rolling summary (via the cheap/fast model) and drops them,
keeping only the last few verbatim. Mirrors the reference chatbot's sliding
-window memory node.
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)

from app.core.config import get_settings

_SUMMARY_SYSTEM = (
    "You compress a travel-assistant conversation into a concise running summary. "
    "Preserve concrete facts the assistant will need later: destinations, dates, "
    "budget, booked items, stated preferences and constraints. Be terse."
)


def should_summarize(messages: list[BaseMessage], threshold: int | None = None) -> bool:
    """True when the thread is long enough to compress.

    :param messages: The current conversation history.
    :param threshold: Override for the message-count threshold; defaults to
        ``settings.summarize_threshold`` when omitted.
    :return: True when ``messages`` exceeds the threshold.
    """
    limit = threshold if threshold is not None else get_settings().summarize_threshold
    return len(messages) > limit


def summarize_conversation(
    messages: list[BaseMessage],
    llm: BaseChatModel,
    *,
    keep_last: int = 5,
) -> tuple[str, list[RemoveMessage]]:
    """Return (summary_text, messages_to_remove).

    The caller writes ``summary_text`` into state and applies the
    ``RemoveMessage`` list (LangGraph's deletion sentinel) to trim history.

    :param messages: The full conversation history to compress.
    :param llm: The chat model used to generate the summary.
    :param keep_last: Number of trailing messages to keep verbatim (not removed).
    :return: A tuple of the summary text and the messages to remove.
    """
    transcript = "\n".join(
        f"{m.type}: {m.content}" for m in messages if getattr(m, "content", None)
    )
    summary = llm.invoke(
        [SystemMessage(content=_SUMMARY_SYSTEM), HumanMessage(content=transcript)]
    ).content
    to_remove = [
        RemoveMessage(id=m.id) for m in messages[:-keep_last] if getattr(m, "id", None)
    ]
    return summary, to_remove
