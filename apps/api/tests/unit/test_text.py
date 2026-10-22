"""Unit tests for the fuzzy text matcher (app/core/text.py)."""

from app.core.text import best_match, fuzzy_filter, match_score
from app.data.countries import COUNTRIES

# --- match_score -------------------------------------------------------------


def test_match_score_exact_is_one():
    assert match_score("Bangkok", "Bangkok") == 1.0


def test_match_score_is_case_insensitive():
    assert match_score("bangkok", "BANGKOK") == 1.0


def test_match_score_prefix_beats_substring():
    # "Mai" alone is only 3 chars -- below the token-prefix substring floor -- so use a
    # 4+ char second word to exercise the substring path (word-start match) here.
    prefix = match_score("New", "New York City")
    substring = match_score("York", "New York City")
    assert prefix > substring > 0.0


def test_match_score_short_substring_does_not_hijack():
    # A short query ("us") must not match merely because it appears inside a longer
    # candidate ("australia") -- this is exactly the bug the token-prefix rule closes.
    assert match_score("us", "Australia") == 0.0
    assert match_score("usa", "Chad") == 0.0


def test_match_score_token_prefix_substring_scores():
    # A 4+ char query that prefixes a later word in the candidate still counts as a
    # substring hit.
    assert match_score("Minh", "Ho Chi Minh City") == 0.8


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


def test_match_score_floor_rejects_below_075():
    # "Chile" vs "China" (ratio 0.6) used to clear the old 0.6 floor; the raised
    # 0.75 floor now correctly treats them as unrelated.
    assert match_score("Chile", "China") == 0.0
    assert match_score("Chad", "China") == 0.0
    assert match_score("Czechia", "China") == 0.0


_COUNTRY_NAMES = [c["name"] for c in COUNTRIES]


def test_best_match_country_regressions():
    # Regression coverage for names that used to be hijacked by an unrelated seeded
    # country once 20 new cities / 10 new countries were added.
    assert best_match("Chile", _COUNTRY_NAMES, [lambda c: c]) is None
    assert best_match("Chad", _COUNTRY_NAMES, [lambda c: c]) is None
    assert best_match("Czechia", _COUNTRY_NAMES, [lambda c: c]) is None
    assert best_match("Sapa", _COUNTRY_NAMES, [lambda c: c]) is None
    assert best_match("Sa Pa", _COUNTRY_NAMES, [lambda c: c]) is None
    assert best_match("Porto", _COUNTRY_NAMES, [lambda c: c]) is None
    assert best_match("Brisbane", _COUNTRY_NAMES, [lambda c: c]) is None
    assert best_match("Berlin", _COUNTRY_NAMES, [lambda c: c]) is None
    assert best_match("Mumbai", _COUNTRY_NAMES, [lambda c: c]) is None
    assert best_match("Dublin", _COUNTRY_NAMES, [lambda c: c]) is None
    # A bare "US"/"USA" must not fuzzy-hijack an unrelated country either (alias
    # resolution, tested separately, is how a resolver should handle it instead).
    assert best_match("US", _COUNTRY_NAMES, [lambda c: c]) is None


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


def test_different_first_letter_is_not_a_typo():
    assert best_match("Hangzhou", ["Guangzhou", "Hanoi"], [lambda c: c]) is None


def test_ratio_at_the_floor_is_not_a_match():
    assert best_match("USA", ["Busan", "Sydney"], [lambda c: c]) is None


def test_same_first_letter_typos_still_match():
    cities = ["Hanoi", "Bangkok", "Singapore", "Tokyo", "Seoul"]
    for typo, city in [
        ("Hanoy", "Hanoi"),
        ("Bankok", "Bangkok"),
        ("Singapor", "Singapore"),
        ("Tokio", "Tokyo"),
        ("Seul", "Seoul"),
    ]:
        assert best_match(typo, cities, [lambda c: c]) == city


# --- rebalance regressions: F1 multi-word interior fragments -----------------


def test_multi_word_fragment_matches_inside_longer_candidate():
    assert (
        best_match("Chi Minh", ["Ho Chi Minh City", "Hanoi"], [lambda c: c])
        == "Ho Chi Minh City"
    )
    assert (
        best_match(
            "Charles de Gaulle",
            ["Paris Charles de Gaulle Airport", "Paris Orly Airport"],
            [lambda c: c],
        )
        == "Paris Charles de Gaulle Airport"
    )
    assert (
        best_match(
            "Golden Bridge",
            ["Ba Na Hills & Golden Bridge", "Dragon Bridge"],
            [lambda c: c],
        )
        == "Ba Na Hills & Golden Bridge"
    )
    assert (
        best_match(
            "Ritz Carlton",
            ["The Ritz-Carlton Tokyo", "Park Hyatt Tokyo"],
            [lambda c: c],
        )
        == "The Ritz-Carlton Tokyo"
    )


def test_hyphen_collapsed_prefix_matches():
    assert (
        best_match("Sensoji", ["Senso-ji Temple", "Meiji Shrine"], [lambda c: c])
        == "Senso-ji Temple"
    )


# --- rebalance regressions: F2 "<City>, <Country>" ---------------------------


def test_city_comma_country_matches_the_city():
    cities = ["Da Nang", "Hanoi", "Bangkok"]
    assert best_match("Da Nang, Vietnam", cities, [lambda c: c]) == "Da Nang"
    assert best_match("Da Nang Vietnam", cities, [lambda c: c]) == "Da Nang"
    assert best_match("Bangkok, Thailand", cities, [lambda c: c]) == "Bangkok"


# --- rebalance regressions: F3 ratio == 0.75 boundary -------------------------


def test_ratio_exactly_at_floor_still_matches():
    for typo, city in [
        ("Roma", "Rome"),
        ("Jeju", "Jeju"),
        ("Vinh", "Vinh"),
        ("Bali", "Bali"),
        ("Cebu", "Cebu"),
        ("Dili", "Dili"),
    ]:
        assert match_score(typo, city) >= 0.75


# --- rebalance regressions: F4 3-letter word-start tokens ---------------------


def test_three_letter_word_start_token_matches():
    cities = ["Can Tho", "Da Lat", "My Son", "Hat Yai"]
    assert best_match("Tho", cities, [lambda c: c]) == "Can Tho"
    assert best_match("Lat", cities, [lambda c: c]) == "Da Lat"
    assert best_match("Son", cities, [lambda c: c]) == "My Son"
    assert best_match("Yai", cities, [lambda c: c]) == "Hat Yai"
    assert (
        best_match(
            "Bai",
            ["Noi Bai International Airport", "Tan Son Nhat International Airport"],
            [lambda c: c],
        )
        == "Noi Bai International Airport"
    )


# --- rebalance regressions: must-stay-rejected --------------------------------


def test_must_stay_rejected_country_hijacks():
    countries = _COUNTRY_NAMES
    for query in [
        "US",
        "Britain",
        "Chile",
        "Chad",
        "Czechia",
        "Sapa",
        "Sa Pa",
        "USA",
        "Porto",
        "Brisbane",
        "Hangzhou",
        "Suzhou",
        "Berlin",
        "Mumbai",
        "Dublin",
        "Saigon",
    ]:
        assert best_match(query, countries, [lambda c: c]) is None


def test_longer_contained_name_wins_the_tie():
    cities = ["Angeles", "Los Angeles"]
    assert (
        best_match("Los Angeles, United States", cities, [lambda c: c]) == "Los Angeles"
    )


def test_name_before_the_comma_matches_a_short_city():
    assert best_match("Hue, Vietnam", ["Hue", "Hanoi"], [lambda c: c]) == "Hue"


# --- final fix pass: F1 a strong typo isn't capped by a weaker rule ----------


def test_typo_ratio_not_capped_by_a_weaker_containment_match():
    # "Lo Angeles" is a token-prefix/word-start hit (0.8) against "Los Angeles" and a
    # containment hit (0.851) against "Angeles", but the difflib ratio against "Los
    # Angeles" (0.952) is the strongest signal and must win the pick.
    assert (
        best_match("Lo Angeles", ["Los Angeles", "Angeles"], [lambda c: c])
        == "Los Angeles"
    )
    assert match_score("Lo Angeles", "Los Angeles") > match_score(
        "Lo Angeles", "Angeles"
    )
    assert (
        best_match("faifocoffee", ["Faifo Coffee", "Hoi An"], [lambda c: c])
        == "Faifo Coffee"
    )


# --- final fix pass: F2 lower containment floor recovers "<City> <Country>" --


def test_short_city_matches_with_trailing_country_word():
    assert best_match("Hue Vietnam", ["Hue", "Hanoi"], [lambda c: c]) == "Hue"
    assert best_match("hotels in Hue", ["Hue", "Hanoi"], [lambda c: c]) == "Hue"


# --- final fix pass: F3 difflib only runs against 4+ char candidates ---------


def test_short_candidate_does_not_take_the_difflib_path():
    # "huket" clears the 0.75 ratio floor against "Hue" purely because both strings are
    # short -- the fuzzy fallback must not fire for a 3-char candidate.
    assert match_score("huket", "Hue") == 0.0
    assert best_match("huket", ["Hue", "Hanoi"], [lambda c: c]) is None
