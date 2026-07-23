"""Unit tests for the fuzzy text matcher (app/core/text.py)."""

from app.core.text import fuzzy_filter, match_score

# --- match_score -------------------------------------------------------------


def test_match_score_exact_is_one():
    assert match_score("Bangkok", "Bangkok") == 1.0


def test_match_score_is_case_insensitive():
    assert match_score("bangkok", "BANGKOK") == 1.0


def test_match_score_prefix_beats_substring():
    prefix = match_score("Chi", "Chiang Mai")
    substring = match_score("Mai", "Chiang Mai")
    assert prefix > substring > 0.0


def test_match_score_empty_query_matches_anything():
    assert match_score("", "anything") == 1.0


def test_match_score_typo_still_scores():
    assert match_score("Bangok", "Bangkok") > 0.0


def test_match_score_unrelated_is_zero():
    assert match_score("xyzzy", "Bangkok") == 0.0


def test_match_score_folds_vietnamese_diacritics():
    # An accented free-text query folds to the ASCII seed spelling (exact match).
    assert match_score("Đà Nẵng", "Da Nang") == 1.0
    assert match_score("Huế", "Hue") == 1.0
    assert match_score("Cần Thơ", "Can Tho") == 1.0


# --- fuzzy_filter ------------------------------------------------------------


class _Item:
    def __init__(self, name, country):
        self.name = name
        self.country = country


_ITEMS = [
    _Item("Bangkok", "Thailand"),
    _Item("Chiang Mai", "Thailand"),
    _Item("Da Nang", "Vietnam"),
    _Item("Hanoi", "Vietnam"),
]
_KEYS = [lambda i: i.name, lambda i: i.country]


def test_fuzzy_filter_empty_query_returns_all_unchanged():
    assert fuzzy_filter("", _ITEMS, _KEYS) == _ITEMS
    assert fuzzy_filter(None, _ITEMS, _KEYS) == _ITEMS


def test_fuzzy_filter_ranks_best_match_first():
    results = fuzzy_filter("Bangok", _ITEMS, _KEYS)
    assert results[0].name == "Bangkok"


def test_fuzzy_filter_drops_non_matches():
    results = fuzzy_filter("Bangkok", _ITEMS, _KEYS)
    assert [i.name for i in results] == ["Bangkok"]


def test_fuzzy_filter_matches_secondary_key():
    results = fuzzy_filter("Vietnam", _ITEMS, _KEYS)
    assert {i.name for i in results} == {"Da Nang", "Hanoi"}


def test_fuzzy_filter_no_match_returns_empty():
    assert fuzzy_filter("zzzznowhere", _ITEMS, _KEYS) == []


def test_fuzzy_filter_resolves_accented_query_to_ascii_seed():
    # "Đà Nẵng" folds to "da nang" → exact match against the ASCII seed.
    assert fuzzy_filter("Đà Nẵng", _ITEMS, _KEYS)[0].name == "Da Nang"
    # "Hà Nội" folds to "ha noi" → strong fuzzy match against seed "Hanoi".
    assert fuzzy_filter("Hà Nội", _ITEMS, _KEYS)[0].name == "Hanoi"
