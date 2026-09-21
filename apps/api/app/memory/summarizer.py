"""Conversation summarisation.

When the message count crosses ``summarize_threshold``, the graph compresses
older turns into a rolling summary and drops them, keeping only the last few
verbatim.
"""

from __future__ import annotations

import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_SUMMARY_SYSTEM = (
    "You compress a travel-assistant conversation into a concise running summary. "
    "Preserve concrete facts the assistant will need later: destinations, dates, "
    "budget, booked items, stated preferences and constraints. Be terse."
)

# When a previous summary is supplied, the task becomes a MERGE rather than a fresh
# summarisation: the older messages it covers have already been deleted from the
# history, so anything dropped here is lost for good. The word cap is what keeps the
# rolling summary from growing without bound as compressions accumulate.
_MERGE_SYSTEM = (
    "You maintain the running summary of a travel-assistant conversation. You are "
    "given the summary so far and the newer messages. Merge them into ONE summary "
    "of at most 250 words. The earlier messages behind the existing summary are "
    "already deleted, so never drop a concrete fact it records: destinations, dates, "
    "budget, booked items, stated preferences and constraints. Prefer dropping "
    "narrative and pleasantries over facts. Be terse."
)


def _safe_split(messages: list[BaseMessage], keep_last: int) -> int:
    """Index where the kept (verbatim) tail should start.

    Walk the naive ``len(messages) - keep_last`` boundary back past any
    ``ToolMessage`` run so a tool-call/tool-result pair is never split across it
    — an orphaned tool result gets rejected by the provider on the next call.
    """
    split = max(len(messages) - keep_last, 0)
    while split > 0 and isinstance(messages[split], ToolMessage):
        split -= 1
    return split


_HEADROOM = 0.85  # leave room for the system prompt and the next reply
# Trailing messages summarize_conversation keeps verbatim. Shared with the token
# branch of should_summarize so the predicate cannot promise a compression the
# compressor is structurally unable to perform.
DEFAULT_KEEP_LAST = 5
# Hard ceiling on the stored rolling summary (~250 words at ~5.5 chars/word, with
# headroom). Enforced in code because _MERGE_SYSTEM can only ask.
_SUMMARY_MAX_CHARS = 1800


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
    # Floor the token branch at the verbatim tail: with keep_last or fewer messages
    # there is nothing summarize_conversation could remove, so claiming "compress
    # this" would be a promise the compressor cannot keep.
    if len(messages) <= DEFAULT_KEEP_LAST:
        return False
    budget = (
        token_budget if token_budget is not None else settings.summarize_token_budget
    )
    return _estimate_tokens(messages) > budget * _HEADROOM


def summarize_conversation(
    messages: list[BaseMessage],
    llm: BaseChatModel,
    *,
    keep_last: int = DEFAULT_KEEP_LAST,
    previous_summary: str | None = None,
) -> tuple[str, list[RemoveMessage]]:
    """Return (summary_text, messages_to_remove).

    The caller writes ``summary_text`` into state and applies the
    ``RemoveMessage`` list (LangGraph's deletion sentinel) to trim history.

    :param messages: The full conversation history to compress.
    :param llm: The chat model used to generate the summary.
    :param keep_last: Minimum number of trailing messages to keep verbatim (not
        removed); more may be kept to avoid splitting a tool-call/tool-result pair.
        **Overriding this decouples it from** ``should_summarize``, which floors its
        token branch at :data:`DEFAULT_KEEP_LAST` and cannot see this argument: a
        caller passing a smaller value gets the token branch suppressed over the range
        between the two, where compression would in fact have been possible.
    :param previous_summary: The rolling summary already in state, if any. When
        given, the result MERGES it with the newer messages instead of replacing it.
        Omitting it is how a repeated compression silently narrows the summary to the
        most recent window while the messages behind it are already deleted — i.e. how
        the agent comes to forget facts stated earlier in the same session.
    :return: A tuple of the summary text and the messages to remove. ``("", [])``
        when nothing is removable — no model call is made in that case.
    """
    # Decide what would actually be removed BEFORE paying for the LLM call. With a
    # short history _safe_split returns 0, so there is nothing to compress and a
    # summary would buy no context relief — while the token branch of
    # should_summarize would keep firing on the same unchanged history, one paid call
    # per turn, forever. Returning early keeps "the node fired" and "the node made
    # progress" the same event, which is what the message-count branch guaranteed
    # structurally and the token branch does not.
    split = _safe_split(messages, keep_last)
    to_remove = [
        RemoveMessage(id=m.id) for m in messages[:split] if getattr(m, "id", None)
    ]
    if not to_remove:
        return "", []

    transcript = "\n".join(
        f"{m.type}: {m.content}" for m in messages if getattr(m, "content", None)
    )
    if previous_summary:
        system = _MERGE_SYSTEM
        payload = (
            f"Summary so far:\n{previous_summary}\n\nNewer messages:\n{transcript}"
        )
    else:
        system = _SUMMARY_SYSTEM
        payload = transcript
    summary = llm.invoke(
        [SystemMessage(content=system), HumanMessage(content=payload)]
    ).content
    # F4: the merge prompt ASKS for at most 250 words; a prompt is a request, not a
    # bound. Without a code-side cap a model that ignores it compounds the summary on
    # every merge, which is the growth this feature exists to prevent.
    #
    # This is a LAST-RESORT bound, not a safe one. _MERGE_SYSTEM says nothing about
    # ordering, so there is no guarantee the carried-forward facts survive in the kept
    # prefix — a runaway merge that trails its facts loses them for good, because the
    # source messages are already RemoveMessage'd. Hence the warning: if this fires in
    # production it means the summary is being maintained by truncation, which is a
    # problem to fix at the prompt, not a steady state to accept.
    if not isinstance(summary, str):
        # A non-string content (multimodal block list) would otherwise bypass the cap
        # entirely and land in state["summary"] as a non-string.
        summary = str(summary)
    if len(summary) > _SUMMARY_MAX_CHARS:
        logger.warning(
            "[agent] summarize: merged summary hit the %d-char cap (was %d); facts "
            "may have been truncated — tighten _MERGE_SYSTEM rather than the cap",
            _SUMMARY_MAX_CHARS,
            len(summary),
        )
        summary = summary[:_SUMMARY_MAX_CHARS].rstrip() + "…"
    return summary, to_remove
