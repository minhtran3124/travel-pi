"""Lightweight fuzzy text matching for query-by-name endpoints.

Agents (and humans) rarely send a perfectly-spelled city or airport name,
so the list endpoints accept a free-text ``q`` and rank candidates by
closeness rather than demanding an exact match. No external dependency —
just the stdlib ``difflib``.
"""

import difflib
import unicodedata
from collections.abc import Callable, Iterable
from typing import TypeVar

T = TypeVar("T")

# Below this difflib similarity ratio a candidate is treated as "no match".
_FUZZY_THRESHOLD = 0.6


def fold_diacritics(text: str) -> str:
    """Fold Vietnamese (and other Latin) diacritics to their base ASCII letters.

    Shared by :mod:`app.core.text` (fuzzy city/airport matching) and
    :mod:`app.core.dates` (weekday/phrase matching), so an accented seed name
    ("Đà Nẵng") or date phrase ("thứ Sáu") matches its unaccented form ("Da
    Nang", "thu sau") against a single dictionary/threshold, instead of
    doubling every entry. ``đ`` (U+0111) has no canonical NFD decomposition,
    so it is mapped explicitly; the remaining Vietnamese/Latin accents (à, ẵ,
    ế, …) decompose to a base letter plus a combining mark, which is then
    dropped.

    :param text: The text to fold (case is left as-is; callers typically
        lowercase first).
    :return: The diacritic-folded text.
    """
    folded = text.replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", folded)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _norm(text: str) -> str:
    """Normalise for comparison: trim, lowercase, and fold diacritics.

    Folding lets an accented free-text query ("Đà Nẵng") match an ASCII seed
    name ("Da Nang") — without it, difflib scores the two below the match
    threshold and the lookup wrongly returns nothing.

    :param text: The raw text to normalise.
    :return: The trimmed, lowercased, diacritic-folded text.
    """
    return fold_diacritics(text.strip().lower())


def match_score(query: str, candidate: str) -> float:
    """Return a 0.0–1.0 relevance score for ``query`` against ``candidate``.

    An exact match scores 1.0, a prefix 0.9, any substring 0.8, and anything
    else falls back to a difflib similarity ratio. Ratios below
    :data:`_FUZZY_THRESHOLD` are flattened to 0.0 ("no match"). An empty
    query matches everything (score 1.0).

    :param query: The free-text search query.
    :param candidate: The candidate string to score against.
    :return: A relevance score between 0.0 (no match) and 1.0 (exact match).
    """
    q, c = _norm(query), _norm(candidate)
    if not q:
        return 1.0
    if q == c:
        return 1.0
    if c.startswith(q):
        return 0.9
    if q in c:
        return 0.8
    ratio = difflib.SequenceMatcher(None, q, c).ratio()
    return ratio if ratio >= _FUZZY_THRESHOLD else 0.0


def fuzzy_filter(
    query: str | None,
    items: Iterable[T],
    keys: list[Callable[[T], str]],
) -> list[T]:
    """Filter and rank ``items`` by how well any of ``keys`` matches ``query``.

    ``keys`` maps an item to its searchable string fields; an item's score
    is the best score across its keys. Items scoring 0.0 are dropped, and
    the survivors come back sorted best-match-first (stable for ties). An
    empty or whitespace-only ``query`` returns ``items`` unchanged.

    :param query: The free-text search query, or None.
    :param items: The candidate items to filter and rank.
    :param keys: Accessors mapping an item to a searchable string field.
    :return: ``items`` filtered to matches and sorted best-match-first.
    """
    items = list(items)
    if not query or not query.strip():
        return items
    scored = [
        (max(match_score(query, key(item)) for key in keys), item) for item in items
    ]
    matches = [(score, item) for score, item in scored if score > 0.0]
    matches.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in matches]


def best_match(
    query: str | None,
    items: Iterable[T],
    keys: list[Callable[[T], str]],
) -> T | None:
    """Return the single best fuzzy match for ``query``, or ``None``.

    A thin wrapper over :func:`fuzzy_filter` for "resolve this free-text
    name to one canonical record" lookups. Unlike ``fuzzy_filter``, an
    empty/whitespace query yields ``None`` (not the first item), so callers
    can treat "no input" and "no match" the same way.

    :param query: The free-text search query, or None.
    :param items: The candidate items to search.
    :param keys: Accessors mapping an item to a searchable string field.
    :return: The best-matching item, or None if no match / no query.
    """
    if not query or not query.strip():
        return None
    matches = fuzzy_filter(query, items, keys)
    return matches[0] if matches else None
