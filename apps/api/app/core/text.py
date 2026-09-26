"""Lightweight fuzzy text matching (stdlib ``difflib``) for query-by-name endpoints."""

import difflib
import re
import unicodedata
from collections.abc import Callable, Iterable
from typing import TypeVar

T = TypeVar("T")

# At or below this difflib similarity ratio a candidate is treated as "no match".
_FUZZY_THRESHOLD = 0.75

# A substring hit only counts as a real match when the query is at least this long -
# shorter queries ("us", "uk") otherwise hijack unrelated candidates that merely contain them.
_MIN_SUBSTRING_LEN = 3

# A token is only meaningful for the token-prefix rule at this length or longer -
# a bare 1-char token ("a", "de") is too common to anchor a match on its own.
_MIN_TOKEN_LEN = 2

# The containment rule (candidate's tokens found intact inside the query, e.g. a
# "<City>, <Country>" query) only fires for candidates at least this long, so short
# candidates ("US") can't hijack via containment either.
_MIN_CONTAINMENT_LEN = 4

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def fold_diacritics(text: str) -> str:
    """Fold Vietnamese/Latin diacritics to base ASCII (``đ`` has no NFD decomposition so it is mapped explicitly; other accents decompose and their combining mark is dropped)."""
    folded = text.replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", folded)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _norm(text: str) -> str:
    """Normalise for comparison: trim, lowercase, fold diacritics so an accented query matches an ASCII seed name."""
    return fold_diacritics(text.strip().lower())


def _collapse(text: str) -> str:
    """Drop hyphens/spaces so "senso-ji temple" and "sensoji" line up as the same run of letters."""
    return text.replace("-", "").replace(" ", "")


def _tokens(text: str) -> list[str]:
    """Split normalised text on any non-alphanumeric run."""
    return _TOKEN_RE.findall(text)


def _word_start_hit(q: str, c: str) -> bool:
    """A substring hit only counts when ``q`` is long enough to be meaningful and matches at the
    start of some word in ``c`` -- so "us" doesn't hijack "australia" and "usa" doesn't hijack "busan"."""
    return len(q) >= _MIN_SUBSTRING_LEN and any(
        word.startswith(q) for word in c.split()
    )


def _token_prefix_hit(q_tokens: list[str], c_tokens: list[str]) -> bool:
    """Every meaningful query token (>= :data:`_MIN_TOKEN_LEN` chars) is a prefix of some
    candidate token -- covers a multi-word fragment like "chi minh" against "ho chi minh city"
    or "ritz carlton" against "the ritz-carlton tokyo"."""
    meaningful = [t for t in q_tokens if len(t) >= _MIN_TOKEN_LEN]
    if not meaningful:
        return False
    return all(any(ct.startswith(qt) for ct in c_tokens) for qt in meaningful)


def _contains_token_sequence(q_tokens: list[str], c_tokens: list[str]) -> bool:
    """The candidate's whole token sequence appears as a contiguous, word-bounded run inside
    the query's tokens -- covers "<City>, <Country>" / "<City> <Country>" queries."""
    if not c_tokens:
        return False
    n = len(c_tokens)
    return any(q_tokens[i : i + n] == c_tokens for i in range(len(q_tokens) - n + 1))


def match_score(query: str, candidate: str) -> float:
    """Return a 0.0-1.0 relevance score: exact 1.0, "<candidate>, …" 0.95, prefix 0.9,
    candidate-contained-in-query ~0.85 (longer names first), token-prefix substring 0.8, else difflib ratio for a same-first-letter candidate
    (below :data:`_FUZZY_THRESHOLD` -> 0.0); an empty query scores 1.0."""
    q, c = _norm(query), _norm(candidate)
    if not q:
        return 1.0
    if q == c:
        return 1.0
    if c.startswith(q) or _collapse(c).startswith(_collapse(q)):
        return 0.9

    # "Hue, Vietnam": the part before the first comma names the candidate exactly.
    if "," in q and q.split(",", 1)[0].strip() == c:
        return 0.95

    q_tokens, c_tokens = _tokens(q), _tokens(c)
    if len(c) >= _MIN_CONTAINMENT_LEN and _contains_token_sequence(q_tokens, c_tokens):
        # The longer contained name wins a tie ("Los Angeles, United States" over "Angeles").
        return 0.85 + min(len(c_tokens), 5) / 1000
    if _token_prefix_hit(q_tokens, c_tokens) or _word_start_hit(q, c):
        return 0.8

    # A typo rarely changes the first letter; different first letters are usually different
    # places that merely share a suffix (Hangzhou/Guangzhou).
    if q[0] != c[0]:
        return 0.0
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
