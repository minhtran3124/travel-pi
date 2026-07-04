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
    ToolMessage,
)

from app.core.config import get_settings

_SUMMARY_SYSTEM = (
    "You compress a travel-assistant conversation into a concise running summary. "
    "Preserve concrete facts the assistant will need later: destinations, dates, "
    "budget, booked items, stated preferences and constraints. Be terse."
)


def _safe_split(messages: list[BaseMessage], keep_last: int) -> int:
    """Index into ``messages`` where the kept (verbatim) tail should start.

    A naive ``len(messages) - keep_last`` can land in the middle of an
    AIMessage-with-``tool_calls`` + its ``ToolMessage`` response(s): if the
    ToolMessage lands in the kept tail but its parent AIMessage falls in the
    removed portion, the next model call sends an orphaned tool result and the
    provider rejects it ("No tool call found for function call output with
    call_id ..."). Walk the boundary back past any ``ToolMessage`` run so a
    tool-call/tool-result pair is always kept or removed together.

    :param messages: The full conversation history being split.
    :param keep_last: Requested number of trailing messages to keep verbatim.
    :return: The (possibly earlier) index where the kept tail actually starts.
    """
    split = max(len(messages) - keep_last, 0)
    while split > 0 and isinstance(messages[split], ToolMessage):
        split -= 1
    return split


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
    :param keep_last: Minimum number of trailing messages to keep verbatim (not
        removed); more may be kept to avoid splitting a tool-call/tool-result pair.
    :return: A tuple of the summary text and the messages to remove.
    """
    transcript = "\n".join(
        f"{m.type}: {m.content}" for m in messages if getattr(m, "content", None)
    )
    summary = llm.invoke(
        [SystemMessage(content=_SUMMARY_SYSTEM), HumanMessage(content=transcript)]
    ).content
    split = _safe_split(messages, keep_last)
    to_remove = [
        RemoveMessage(id=m.id) for m in messages[:split] if getattr(m, "id", None)
    ]
    return summary, to_remove
