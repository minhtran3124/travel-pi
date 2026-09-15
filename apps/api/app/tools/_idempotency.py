"""Turn-scoped idempotency key for write tools (gh-193, task 1.1).

``book_flight`` / ``book_hotel`` are called again on a revise turn (the
reflection loop re-runs the specialist with a correction note). Passing a
stable ``idempotency_key`` to ``BookingService.book_*`` lets the service
replay the existing booking for the same owner instead of creating a
duplicate.

The key is scoped to *one traveller turn*: it is derived from the LangGraph
``thread_id`` and the id of the last ``HumanMessage`` (the turn boundary),
plus the tool name and the model-visible args. A later turn (a new
``HumanMessage``) is a genuinely new request and gets a new key. Injected
plumbing (``user_id``, ``trip_id``, ``messages``, ``config``) is stripped
before hashing so it never perturbs the key.

The helper is pure and side-effect free: it imports only stdlib and
``langchain_core`` and reaches nothing from ``app.agents``.
"""

from __future__ import annotations

import hashlib
import json

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from app.exceptions import DUPLICATE_WARNING_MARKER

#: Appended to the refused-override error so the model knows a fresh traveller
#: turn is required before the duplicate can be forced through (gh-194).
OVERRIDE_REFUSED_HINT = (
    "The allow_duplicate override was ignored because the traveller has not "
    "confirmed a second booking since this duplicate was flagged in the current "
    "turn. Tell the traveller about the existing booking and wait for them to "
    "confirm in a new message before booking again."
)

# Injected/config parameter names that are supplied by the graph, not the
# model. They are dropped from ``args`` before canonicalisation so the same
# traveller-visible call always hashes to the same key regardless of whether
# the graph happened to pass injected values in.
INJECTED_ARG_NAMES = frozenset({"user_id", "trip_id", "messages", "config"})


def _thread_id(config: RunnableConfig | None) -> str | None:
    if not config:
        return None
    thread_id = config.get("configurable", {}).get("thread_id")
    return thread_id or None


def _last_human_index(messages: list | None) -> int | None:
    """Index of the most recent ``HumanMessage`` (the turn boundary), or None."""
    if not messages:
        return None
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            return i
    return None


def _last_human_message_id(messages: list | None) -> str | None:
    index = _last_human_index(messages)
    if index is None:
        return None
    return messages[index].id or None


def _message_text(content: object) -> str:
    """Flatten a message ``content`` (str or list-of-parts) to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text", "")))
        return " ".join(parts)
    return str(content)


def duplicate_warned_this_turn(tool_name: str, messages: list | None) -> bool:
    """Was a duplicate warning already surfaced for ``tool_name`` this turn?

    Scans the messages *after* the most recent ``HumanMessage`` (the turn
    boundary) for an error :class:`~langchain_core.messages.ToolMessage` from the
    same tool whose content carries
    :data:`~app.exceptions.DUPLICATE_WARNING_MARKER`. A True result means the
    traveller has NOT spoken since the warning, so an ``allow_duplicate`` override
    in the same turn must be ignored (gh-194): the first duplicate call raised
    before any row was inserted, so idempotency replay cannot catch a same-turn
    re-run with a flipped flag.

    :param tool_name: The calling tool's name (``"book_flight"`` / ``"book_hotel"``).
    :param messages: The injected graph message list. ``None``/empty (no context)
        returns False — the override is honoured, today's behaviour.
    :return: True if a same-turn duplicate warning from this tool is present.
    """
    if not messages:
        return False
    start = (_last_human_index(messages) or -1) + 1
    for message in messages[start:]:
        if (
            isinstance(message, ToolMessage)
            and getattr(message, "name", None) == tool_name
            and getattr(message, "status", None) == "error"
            and DUPLICATE_WARNING_MARKER in _message_text(message.content)
        ):
            return True
    return False


def turn_idempotency_key(
    tool_name: str,
    args: dict,
    *,
    user_id: str,
    config: RunnableConfig | None,
    messages: list | None,
) -> str | None:
    """Derive a stable idempotency key for one write-tool call within a turn.

    :param tool_name: The calling tool's name (distinguishes e.g. ``book_flight``
        from ``book_hotel`` on the same turn).
    :param args: The tool's arguments; injected/config names in
        :data:`INJECTED_ARG_NAMES` are dropped before hashing.
    :param user_id: The booking owner (injected from graph state).
    :param config: The LangChain ``RunnableConfig``; ``thread_id`` is read from
        ``config["configurable"]["thread_id"]``.
    :param messages: The graph message list; the last ``HumanMessage`` marks the
        turn boundary.
    :return: A sha256 hex digest, or ``None`` when the turn cannot be
        identified (no thread id, or no last ``HumanMessage``) — the caller then
        books without a key, exactly as before.
    """
    thread_id = _thread_id(config)
    human_id = _last_human_message_id(messages)
    if not thread_id or not human_id:
        return None

    model_visible_args = {k: v for k, v in args.items() if k not in INJECTED_ARG_NAMES}
    canonical_args = json.dumps(
        model_visible_args, sort_keys=True, separators=(",", ":"), default=str
    )
    parts = [user_id, thread_id, human_id, tool_name, canonical_args]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
