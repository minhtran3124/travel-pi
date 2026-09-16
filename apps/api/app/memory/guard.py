"""Deterministic guard for long-term memory (specs/memory-poisoning-hardening §3.1).

Persistent memory is re-injected into every future system prompt, so a single
turn saying "from now on always …" — typed by the traveller or smuggled via
tool output — can become a permanent directive. This module is the pure,
side-effect-free filter that stands between the extractor / tools and the
store: a key allowlist, a length cap, and an EN + VI pattern blocklist. No LLM
judge, no network, no store access (a later task makes the store import *this*
module — importing the store here would be a cycle).

Two modes share one implementation of the content rules (B4):

- :func:`check` — the **write** path. Enforces the per-kind key allowlist
  (episodes: a slug shape rule) and every content rule; raises
  :class:`MemoryRejected` on any violation.
- :func:`check_content` — the **read** path. The key need only match the shape
  rule (so harmless legacy keys survive, B4); over-length text is *truncated*
  to the cap rather than rejected. Callers MUST use the returned text, never
  the stored original — that is what keeps ``<``/``>`` out of the prompt for
  rows written before this guard existed.

The blocklist is one layer of defence-in-depth, known to be bypassable; the
allowlist + length cap + prompt wrapping are the primary controls. Reject
reasons name the rule (``key_not_allowed``, ``too_long``,
``blocked_pattern:<category>``, ``empty``) and never echo the memory text.
"""

from __future__ import annotations

import re
from typing import Literal

from app.core.text import fold_diacritics
from app.exceptions import AppError

#: The guard's memory kinds. These map to the store namespaces (``prefs``,
#: ``procedural``, ``episodes``) at the store layer (§3.2), not here.
MemoryKindLiteral = Literal["preferences", "instructions", "episodes"]


class MemoryRejected(AppError):
    """A memory item failed the guard and must not be stored / surfaced (HTTP 422).

    Subclasses :class:`~app.exceptions.AppError` so it never defaults to a 500;
    in practice every caller catches it (extractor, tools, read helpers) and it
    never reaches an HTTP response. :attr:`reason` names the rule that fired
    (``key_not_allowed``, ``too_long``, ``blocked_pattern:<category>``,
    ``empty``) and deliberately never carries the rejected text.
    """

    status_code = 422
    default_detail = "Memory item rejected"

    def __init__(self, reason: str) -> None:
        #: The rule that rejected the item — safe to log (no memory text).
        self.reason = reason
        super().__init__(reason)


# --- Key allowlists (exported: one source of truth for schemas + prompts) ----

# Reserved personalization keys — defined here (not imported from
# ``store.py``) to avoid an import cycle; kept in store.py:152 order.
PROFILE_KEYS: tuple[str, ...] = ("name", "gender", "travel_group")

#: Canonical preference keys accepted on write. Includes :data:`PROFILE_KEYS`
#: intentionally (the tool already accepts any key today — this narrows, it
#: does not grant a new capability).
PREFERENCE_KEYS: tuple[str, ...] = (
    "diet",
    "hotel_type",
    "airline",
    "cabin_class",
    "budget_band",
    "seat",
    "travel_pace",
    "language",
    "price_currency",
    "accessibility",
) + PROFILE_KEYS

#: Canonical standing-instruction keys accepted on write (B3: a small closed
#: set; unknown instruction keys are rejected).
INSTRUCTION_KEYS: tuple[str, ...] = (
    "reply_length",
    "reply_tone",
    "address_as",
    "price_display",
    "exclude_options",
    "format",
)

_ALLOWED_KEYS: dict[str, tuple[str, ...]] = {
    "preferences": PREFERENCE_KEYS,
    "instructions": INSTRUCTION_KEYS,
}

# Trip id / slug shape — the write shape for episode keys and the read shape
# for every kind (a legacy key with ``<``, ``:`` or spaces is dropped on read).
_KEY_SHAPE_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")

#: Text length caps (after normalization), per kind.
_TEXT_CAP: dict[str, int] = {
    "preferences": 200,
    "instructions": 200,
    "episodes": 400,
}

_CITY_CAP = 60
_EPISODE_OUTCOMES = frozenset({"proposed", "approved"})


# --- Blocklist (EN + VI), matched on fold_diacritics(text.lower()) -----------

# Ordered (category, compiled pattern) pairs; the first match names the reason.
# ``re.MULTILINE`` so line-leading role-spoofing (``system:`` …) anchors per
# line. Patterns assume already-lowercased, diacritic-folded input (đ→d).
_BLOCKLIST: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "instruction_override",
        re.compile(
            r"(ignore|disregard|forget)\s+((all|any|previous|prior|above)\s+)+"
            r"(instructions|rules)"
            r"|bo qua\s+(moi\s+|cac\s+)?(huong dan|chi dan|quy tac)"
        ),
    ),
    (
        "role_change",
        re.compile(
            r"you are now"
            r"|act as\s+(if|though)\b"
            r"|act as\s+(an?\s+|the\s+)?"
            r"(ai|assistant|system|developer|admin|unrestricted|jailbroken)\b"
            r"|pretend\s+(to be|you)"
            r"|tu gio ban la"
            r"|dong vai\s+(la\s+)?(ai|tro ly|he thong)"
        ),
    ),
    (
        "prompt_exfiltration",
        re.compile(
            r"system prompt"
            r"|(reveal|show|print|repeat)\s+(your|the)\s+(instructions|prompt)"
            r"|tiet lo\s+(prompt|huong dan)"
        ),
    ),
    (
        "role_spoofing",
        re.compile(
            r"^\s*(system|assistant|developer)\s*:"
            r"|<\|[^|]*\|>",
            re.MULTILINE,
        ),
    ),
    (
        "policy_bypass",
        re.compile(
            r"developer mode"
            r"|jailbreak"
            r"|no restrictions\s+(on|for)\s+(you|the assistant|your)"
            r"|(answer|respond|reply)\s+without\s+(any\s+)?"
            r"(limits|restrictions|filters)"
        ),
    ),
)


def _run_blocklist(text: str) -> None:
    """Raise :class:`MemoryRejected` if *text* trips any blocklist category.

    Matches against a lower-cased, diacritic-folded copy so an accented VI
    injection ("bỏ qua mọi hướng dẫn") and its folded form match one pattern.

    :param text: A whitespace-collapsed memory form to scan. :func:`_normalize_text`
        calls this twice — once on the form that still contains ``<``/``>`` (so
        role-spoofing tokens like ``<|…|>`` stay visible) and once on the form
        with brackets removed and re-collapsed (so a ``<>``-insertion cannot mask
        a pattern).
    """
    folded = fold_diacritics(text.lower())
    for category, pattern in _BLOCKLIST:
        if pattern.search(folded):
            raise MemoryRejected(f"blocked_pattern:{category}")


def _normalize_text(text: str) -> str:
    """Collapse whitespace + strip, run the blocklist on both bracket forms, remove ``<``/``>``.

    Order is load-bearing:

    1. Collapse internal whitespace and strip, so a pattern's literal single
       space matches even when the raw text used a double space or newline.
    2. Build the de-bracketed form: remove ``<``/``>`` and re-collapse whitespace.
    3. Run the blocklist on BOTH forms — a hit in either rejects:
       - the still-bracketed collapsed form, so role-spoofing tokens like
         ``<|…|>`` (which need the brackets to be detectable) still match;
       - the de-bracketed re-collapsed form, so a bracket insertion such as
         ``"you are <>now an admin"`` cannot mask the ``you are now`` pattern.
       Scanning only the bracketed form (the previous ordering) let ``<>``
       insertion slip a pattern past the blocklist and then be stored as the
       exact blocked phrase once the brackets were removed.
    4. Return the de-bracketed form — angle brackets are gone, so stored text
       cannot close a ``<traveller_memory>`` wrapper tag in the system prompt.

    :param text: Raw memory text.
    :return: The normalized text (may be empty).
    :raises MemoryRejected: ``blocked_pattern:<category>`` if either bracket form
        trips a blocklist category.
    """
    collapsed = re.sub(r"\s+", " ", text).strip()
    debracketed = re.sub(
        r"\s+", " ", collapsed.replace("<", "").replace(">", "")
    ).strip()
    _run_blocklist(collapsed)
    _run_blocklist(debracketed)
    return debracketed


def _apply_content(text: str, cap: int, *, truncate: bool) -> str:
    """Run the shared content rules: normalize + blocklist, then empty + length.

    :func:`_normalize_text` runs the blocklist on the full (collapsed but
    un-truncated) text, so over-length poisoned text cannot slip a pattern past
    the cap.

    :param text: Raw memory text.
    :param cap: Maximum allowed length after normalization.
    :param truncate: On read, truncate over-length text to *cap*; on write,
        raise ``too_long`` instead.
    :return: The normalized (and, on read, possibly truncated) text.
    :raises MemoryRejected: ``blocked_pattern:<category>``, ``empty`` or
        ``too_long``.
    """
    normalized = _normalize_text(text)
    if not normalized:
        raise MemoryRejected("empty")
    if len(normalized) > cap:
        if truncate:
            return normalized[:cap]
        raise MemoryRejected("too_long")
    return normalized


def check(kind: MemoryKindLiteral, key: str, text: str) -> str:
    """Write-path guard: key allowlist (episodes: shape rule) + content rules.

    :param kind: The memory kind (``preferences`` / ``instructions`` /
        ``episodes``).
    :param key: The store key. Preferences / instructions must be in the
        canonical allowlist; episodes must match the slug shape rule.
    :param text: The raw memory text to validate and normalize.
    :return: The normalized text safe to store.
    :raises MemoryRejected: ``key_not_allowed``, ``blocked_pattern:<category>``,
        ``empty`` or ``too_long``.
    """
    if kind == "episodes":
        if not _KEY_SHAPE_RE.fullmatch(key):
            raise MemoryRejected("key_not_allowed")
    elif key not in _ALLOWED_KEYS[kind]:
        raise MemoryRejected("key_not_allowed")
    return _apply_content(text, _TEXT_CAP[kind], truncate=False)


def check_content(kind: MemoryKindLiteral, key: str, text: str) -> str:
    """Read-path guard: shape-rule key (no allowlist) + content rules, truncating.

    Harmless legacy rows with non-canonical keys (e.g. ``food_preference``)
    still surface (B4); a legacy key containing ``<``, ``:`` or spaces is
    dropped. Over-length text is truncated to the cap rather than rejected.

    :param kind: The memory kind (selects the length cap).
    :param key: The stored key; must match the shape rule for every kind.
    :param text: The raw stored text.
    :return: The normalized (and possibly truncated) text — callers MUST use
        this, never the stored original.
    :raises MemoryRejected: ``key_not_allowed``, ``blocked_pattern:<category>``
        or ``empty``.
    """
    if not _KEY_SHAPE_RE.fullmatch(key):
        raise MemoryRejected("key_not_allowed")
    return _apply_content(text, _TEXT_CAP[kind], truncate=True)


def check_episode(value: dict) -> dict:
    """Validate/normalize an episode value's extra fields (``city``, ``outcome``).

    The episode ``text`` is guarded separately via :func:`check` /
    :func:`check_content`; this handles the metadata that rides alongside it —
    applied on both write and read (§3.1). ``city`` gets the same blocklist +
    normalization and is capped at 60 chars; ``outcome`` is coerced to
    ``proposed`` unless it is already ``proposed`` / ``approved``.

    :param value: The episode value dict.
    :return: A shallow copy with a coerced ``outcome`` and a normalized ``city``
        (dropped when it normalizes to empty).
    :raises MemoryRejected: ``blocked_pattern:<category>`` if ``city`` trips the
        blocklist.
    """
    cleaned = dict(value)
    outcome = value.get("outcome")
    cleaned["outcome"] = outcome if outcome in _EPISODE_OUTCOMES else "proposed"

    city = value.get("city")
    if isinstance(city, str):
        normalized_city = _normalize_text(city)[:_CITY_CAP]
        if normalized_city:
            cleaned["city"] = normalized_city
        else:
            cleaned.pop("city", None)
    return cleaned


def normalize_episode_key(key: str, trip_id: str | None = None) -> str:
    """Slugify an episode key, falling back to *trip_id* then ``"episode"``.

    Runs *after* the existing ``ep.get("key") or trip_id or "episode"`` fallback
    (extraction_runner.py:94): lowercase, fold diacritics, replace runs of
    non-``[a-z0-9_-]`` with ``_``, and strip leading/trailing ``_`` / ``-`` — so
    ``"Da Nang Trip"`` → ``"da_nang_trip"``. If the result is empty, use a
    slugified *trip_id*; if that is empty too, ``"episode"``.

    :param key: The raw episode key.
    :param trip_id: Fallback trip id used when *key* slugifies to empty.
    :return: A slug suitable for the episodes namespace.
    """
    slug = _slugify(key)
    if slug:
        return slug
    if trip_id:
        trip_slug = _slugify(trip_id)
        if trip_slug:
            return trip_slug
    return "episode"


def _slugify(text: str) -> str:
    """Lowercase, fold diacritics, ``_``-join non-slug runs, strip edges.

    :param text: The raw text to slugify.
    :return: The slug (may be empty).
    """
    folded = fold_diacritics(text.lower())
    collapsed = re.sub(r"[^a-z0-9_-]+", "_", folded)
    return collapsed.strip("_-")
