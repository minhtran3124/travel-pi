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


_HEADROOM = 0.85  # leave room for the system prompt and the next reply


def _content_chars(content: object) -> int:
    """Character length of a message ``content``, tolerating multimodal shapes.

    ``content`` may be a plain string, a list of block dicts (multimodal), or a
    dict. Any non-string shape is stringified so estimation never raises.

    :param content: The ``content`` attribute of a message.
    :return: The character count used to estimate tokens.
    """
    if content is None:
        return 0
    if isinstance(content, str):
        return len(content)
    return len(str(content))


def _estimate_tokens(messages: list[BaseMessage]) -> int:
    """Estimate the token footprint of ``messages`` from character length.

    Uses the portable ``chars / 4`` heuristic and counts **tool-call arguments**
    as well as ``content`` — a fan-out turn carries most of its tokens in tool
    payloads, which a message count misses.

    We deliberately do NOT call ``llm.get_num_tokens_from_messages()``:
    ``transformers`` is not installed in this venv, so ``langchain_core``'s base
    implementation (which falls back to ``GPT2TokenizerFast.from_pretrained("gpt2")``)
    raises for any model that does not override it — including the test ``FakeLLM``.
    This value is only a ceiling, so a provider-coupled count is not worth it.

    :param messages: The conversation history to estimate.
    :return: The estimated token count.
    """
    chars = 0
    for m in messages:
        chars += _content_chars(getattr(m, "content", None))
        for call in getattr(m, "tool_calls", None) or []:
            chars += len(str(call.get("name", "")))
            chars += len(str(call.get("args", "")))
    return chars // 4


def should_summarize(
    messages: list[BaseMessage],
    threshold: int | None = None,
    *,
    token_budget: int | None = None,
) -> bool:
    """True when the thread is long enough or heavy enough to compress.

    Compresses when the message count exceeds ``threshold`` **OR** the estimated
    token count exceeds ``token_budget * 0.85``. The token branch catches
    token-heavy fan-out turns that sit below the message-count threshold; the
    count branch is never bypassed.

    :param messages: The current conversation history.
    :param threshold: Override for the message-count threshold; defaults to
        ``settings.summarize_threshold`` when omitted.
    :param token_budget: Override for the token ceiling; defaults to
        ``settings.summarize_token_budget`` when omitted.
    :return: True when ``messages`` exceeds either threshold.
    """
    settings = get_settings()
    limit = threshold if threshold is not None else settings.summarize_threshold
    if len(messages) > limit:
        return True
    budget = (
        token_budget if token_budget is not None else settings.summarize_token_budget
    )
    return _estimate_tokens(messages) > budget * _HEADROOM


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
