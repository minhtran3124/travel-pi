"""Deterministic preference-aware re-ranking for hotel/flight tool results
(DESIGN.md D7, MIN-65 task 6.2).

Boost-only, stable: never drops or reorders items beyond a descending sort by
match count, and ties keep their original relative order (Python's ``sorted``
is documented stable, including with ``reverse=True``) — so the same query +
the same ``preferences`` text always yields the same output order, matching
the "same query = same result" determinism the search tools already rely on
(MD5-seeded generation).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

from app.core.text import fold_diacritics

T = TypeVar("T")

# One "feature" of an item: alternate keyword phrasings that would indicate the
# traveller wants this feature, plus the human-readable reason to surface in
# the tool's summary if it matched. A feature counts as matched when ANY of
# its keywords appears (case-insensitive, diacritic-folded) in ``preferences``.
KeywordFn = Callable[[T], Iterable[tuple[Iterable[str], str]]]


def rank_by_preference(
    items: list[T], preferences: str, *, keyword_fn: KeywordFn
) -> tuple[list[T], list[str]]:
    """Stable-sort ``items`` descending by preference-keyword match count.

    Keyword matching is a deterministic substring check, not NLP — free-text
    preferences are a known v1 trade-off (DESIGN.md D7). Boost-only: no item
    is ever dropped or filtered, and items with equal scores keep their
    original relative order.

    :param items: The service's result list, already in its own deterministic
        order (e.g. price/date sort) — that order becomes the tiebreaker.
    :param preferences: The formatted preferences text block from graph state
        (``TravelAgentState.preferences``). Empty/blank is a no-op.
    :param keyword_fn: Per-item feature extractor — see :data:`KeywordFn`.
    :return: ``(ranked_items, matched_reasons)``. ``matched_reasons`` lists,
        de-duplicated in first-seen order, the reason for every feature that
        matched at least one item — for the caller to fold into its summary.
    """
    if not preferences or not preferences.strip():
        return items, []
    folded_prefs = fold_diacritics(preferences.lower())

    scores: list[int] = []
    reasons: dict[str, None] = {}
    for item in items:
        score = 0
        for keywords, reason in keyword_fn(item):
            if any(fold_diacritics(str(kw).lower()) in folded_prefs for kw in keywords):
                score += 1
                reasons[reason] = None
        scores.append(score)

    ranked = [
        item
        for _, item in sorted(
            zip(scores, items, strict=True), key=lambda pair: pair[0], reverse=True
        )
    ]
    return ranked, list(reasons)
