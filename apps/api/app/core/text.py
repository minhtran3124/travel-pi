"""Lightweight fuzzy text matching (stdlib ``difflib``) for query-by-name endpoints."""

import difflib
import unicodedata
from collections.abc import Callable, Iterable
from typing import TypeVar

T = TypeVar("T")

# Below this difflib similarity ratio a candidate is treated as "no match".
_FUZZY_THRESHOLD = 0.6


def fold_diacritics(text: str) -> str:
    """Fold Vietnamese/Latin diacritics to base ASCII (``đ`` has no NFD decomposition so it is mapped explicitly; other accents decompose and their combining mark is dropped)."""
    folded = text.replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", folded)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _norm(text: str) -> str:
    """Normalise for comparison: trim, lowercase, fold diacritics so an accented query matches an ASCII seed name."""
    return fold_diacritics(text.strip().lower())


def match_score(query: str, candidate: str) -> float:
    """Return a 0.0–1.0 relevance score: exact 1.0, prefix 0.9, substring 0.8, else difflib ratio (below :data:`_FUZZY_THRESHOLD` → 0.0); an empty query scores 1.0."""
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
    """Filter and rank ``items`` by the best match of any of ``keys`` against ``query`` (0.0 dropped, ties stable); an empty query returns ``items`` unchanged."""
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
    """Return the single best fuzzy match for ``query``, or ``None`` — unlike :func:`fuzzy_filter`, an empty query yields ``None`` so "no input" and "no match" read the same."""
    if not query or not query.strip():
        return None
    matches = fuzzy_filter(query, items, keys)
    return matches[0] if matches else None
