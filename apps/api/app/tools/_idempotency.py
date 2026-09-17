"""Turn-scoped idempotency key for write tools.

The key is scoped to one traveller turn (thread_id + last HumanMessage id + tool + model-visible args)
so a revise re-run replays the existing booking, while a new turn is a genuinely new request. Injected
plumbing is stripped before hashing. The turn guard reads the same window to decide whether an
``allow_duplicate`` override is honoured, per flagged booking id.
"""

from __future__ import annotations

import hashlib
import json

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from app.exceptions import DUPLICATE_WARNING_MARKER_RE

#: Appended to the refused-override error so the model knows a fresh traveller turn is required.
OVERRIDE_REFUSED_HINT = (
    "The allow_duplicate override was ignored because the traveller has not "
    "confirmed a second booking since this duplicate was flagged in the current "
    "turn. Tell the traveller about the existing booking and wait for them to "
    "confirm in a new message before booking again."
)

#: Wildcard for a duplicate warning with no booking id; in the warned set it fails safe by refusing
#: every same-tool override this turn.
DUPLICATE_WARNED_ANY = "*"

# Graph-injected arg names, dropped before hashing so the same traveller-visible call always hashes
# to the same key regardless of injected values.
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


def duplicate_warned_ids_this_turn(
    tool_name: str, messages: list | None
) -> frozenset[str]:
    """Ids of bookings flagged as duplicates for ``tool_name`` since the last HumanMessage.

    An unparseable marker (missing/malformed id) contributes :data:`DUPLICATE_WARNED_ANY` so it never
    lets an override through. A non-empty result means the traveller has not spoken since the warning,
    so a same-turn override must be ignored — the first duplicate raised before any row was inserted,
    so idempotency replay cannot catch a re-run with a flipped flag.
    """
    if not messages:
        return frozenset()
    start = (_last_human_index(messages) or -1) + 1
    warned: set[str] = set()
    for message in messages[start:]:
        if (
            isinstance(message, ToolMessage)
            and getattr(message, "name", None) == tool_name
            and getattr(message, "status", None) == "error"
        ):
            for match in DUPLICATE_WARNING_MARKER_RE.finditer(
                _message_text(message.content)
            ):
                booking_id = match.group(1)
                clean = bool(booking_id) and not any(c.isspace() for c in booking_id)
                warned.add(booking_id if clean else DUPLICATE_WARNED_ANY)
    return frozenset(warned)


def duplicate_override_refused(existing_id: str, warned: frozenset[str]) -> bool:
    """True iff the wildcard is present (id-less warning refuses every override) or ``existing_id`` was
    flagged this turn."""
    return DUPLICATE_WARNED_ANY in warned or existing_id in warned


def duplicate_warned_this_turn(tool_name: str, messages: list | None) -> bool:
    """Was any duplicate warning already surfaced for ``tool_name`` this turn?"""
    return bool(duplicate_warned_ids_this_turn(tool_name, messages))


def turn_idempotency_key(
    tool_name: str,
    args: dict,
    *,
    user_id: str,
    config: RunnableConfig | None,
    messages: list | None,
) -> str | None:
    """Derive a stable idempotency key for one write-tool call within a turn, or ``None`` when the turn
    cannot be identified (no thread id or no last ``HumanMessage``) so the caller books without a key."""
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
