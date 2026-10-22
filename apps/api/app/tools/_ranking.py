"""Deterministic preference-aware re-ranking for hotel/flight tool results.

Boost-only and stable: items are only sorted descending by match count, ties keep their original order,
so the same query and ``preferences`` always yield the same output order.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import TypeVar

from app.core.text import fold_diacritics

T = TypeVar("T")

# Short keywords are too collision-prone to match (e.g. 2-letter IATA airline codes).
_MIN_KEYWORD_LEN = 3


def _keyword_matches(keyword: str, folded_haystack: str) -> bool:
    """Word-boundary match, not a raw substring check: the latter false-positives (e.g. "hotel" inside
    the "hotel_type" preference key, or "KE" inside "weekend")."""
    folded_kw = fold_diacritics(str(keyword).lower()).strip()
    if len(folded_kw) < _MIN_KEYWORD_LEN:
        return False
    return (
        re.search(rf"(?<!\w){re.escape(folded_kw)}(?!\w)", folded_haystack) is not None
    )


# Per item, yields (keyword phrasings, reason); a feature matches when ANY keyword appears in preferences.
KeywordFn = Callable[[T], Iterable[tuple[Iterable[str], str]]]


def rank_by_preference(
    items: list[T], preferences: str, *, keyword_fn: KeywordFn
) -> tuple[list[T], list[str]]:
    """Stable-sort ``items`` descending by preference-keyword match count (deterministic substring
    matching, not NLP). Boost-only: nothing is dropped and equal scores keep their original order.
    Returns ``(ranked_items, matched_reasons)`` with reasons de-duplicated in first-seen order."""
    if not preferences or not preferences.strip():
        return items, []
    folded_prefs = fold_diacritics(preferences.lower())

    scores: list[int] = []
    reasons: dict[str, None] = {}
    for item in items:
        score = 0
        for keywords, reason in keyword_fn(item):
            if any(_keyword_matches(kw, folded_prefs) for kw in keywords):
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
