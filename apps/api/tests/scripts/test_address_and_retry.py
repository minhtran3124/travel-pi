"""Unit tests for the gh-237 final fix pass (F9): ``_resolve_address``,
``_is_latin_text``, the P131 bare-QID-label rejection, and ``_retry_after_seconds``.
No network -- pure functions, table-driven."""

import math

import pytest
from scripts.build_city_sources import _BARE_QID_RE, _is_latin_text, _resolve_address
from scripts.fetch_city_candidates import _BARE_QID_RE as _FETCH_BARE_QID_RE
from scripts.fetch_city_candidates import _retry_after_seconds

# --- _is_latin_text -----------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("112 rue du Faubourg-Saint-Honoré, 75008 Paris, France", True),
        ("Umeda, Osaka", True),
        ("Via Alberto Cadlolo 101, I-00136 Roma", True),
        ("530-0001 大阪府大阪市北区梅田1丁目8-8", False),
        ("〒542-0086　大阪府大阪市中央区西心斎橋1-6-22大石ビル1F", False),
        ("서울특별시 강남구", False),
        ("", True),
    ],
)
def test_is_latin_text(text, expected):
    assert _is_latin_text(text) is expected


# --- _BARE_QID_RE (rejecting a P131 label the label service fell back to) ----


@pytest.mark.parametrize(
    ("label", "is_bare_qid"),
    [
        ("Q60985766", True),
        ("Q1", True),
        ("Osaka", False),
        ("Q60985766 District", False),
        ("QatarQ123", False),
    ],
)
def test_bare_qid_pattern(label, is_bare_qid):
    assert bool(_BARE_QID_RE.match(label)) is is_bare_qid
    # The fetcher (fetch_city_candidates.py) applies the identical pattern.
    assert bool(_FETCH_BARE_QID_RE.match(label)) is is_bare_qid


# --- _resolve_address -----------------------------------------------------------


@pytest.mark.parametrize(
    ("candidate", "city", "expected"),
    [
        # address_en always wins outright.
        (
            {"address_en": "1 Main St, Springfield"},
            "Springfield",
            "1 Main St, Springfield",
        ),
        # A plain district below the city renders "<district>, <city>".
        ({"district_en": "Shibuya"}, "Tokyo", "Shibuya, Tokyo"),
        # District equal to the city (case/whitespace-insensitive) is a no-op -- skip it.
        ({"district_en": "Rome"}, "Rome", "Rome"),
        ({"district_en": "  osaka "}, "Osaka", "Osaka"),
        # District containing the city name as a substring is redundant -- skip it.
        ({"district_en": "Emirate of Dubai"}, "Dubai", "Dubai"),
        ({"district_en": "Los Angeles County"}, "Los Angeles", "Los Angeles"),
        # An admin level above/beside the city (not containing its name) is skipped too.
        ({"district_en": "Shiga Prefecture"}, "Osaka", "Osaka"),
        ({"district_en": "New South Wales"}, "Sydney", "Sydney"),
        ({"district_en": "California"}, "Los Angeles", "Los Angeles"),
        ({"district_en": "Jeju Province"}, "Jeju", "Jeju"),
        # A district that is a bare QID (no English P131 label) is treated as absent.
        ({"district_en": "Q60985766"}, "Sapporo", "Sapporo"),
        # No usable enrichment field: fall back to the raw address, but only if Latin.
        ({"address": "123 High St"}, "London", "123 High St"),
        ({"address": "大阪府大阪市北区梅田1丁目8-8"}, "Osaka", "Osaka"),
        # A skipped district still falls through to a Latin raw address.
        (
            {"district_en": "Osaka", "address": "1 Umeda Ave"},
            "Osaka",
            "1 Umeda Ave",
        ),
        # A curated fallback_address wins over a non-Latin raw address.
        # (passed positionally as fallback_address below)
        ({}, "Hanoi", "Hanoi"),
    ],
)
def test_resolve_address(candidate, city, expected):
    assert _resolve_address(candidate, city) == expected


def test_resolve_address_uses_fallback_address_over_non_latin_raw_address():
    candidate = {"address": "大阪府大阪市北区梅田1丁目8-8"}
    assert (
        _resolve_address(candidate, "Osaka", fallback_address="Curated St, Osaka")
        == "Curated St, Osaka"
    )


def test_resolve_address_falls_back_to_city_with_nothing_available():
    assert _resolve_address({}, "Hanoi") == "Hanoi"


# --- _retry_after_seconds -------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "attempt", "expected"),
    [
        (None, 0, 2.0),
        (None, 2, 6.0),
        ("5", 0, 5.0),
        ("0", 0, 0.0),
        ("-10", 0, 0.0),
        ("9999", 0, 600.0),
        ("inf", 0, 2.0),
        ("nan", 0, 2.0),
        ("not-a-number-or-date", 1, 4.0),
    ],
)
def test_retry_after_seconds_numeric_and_fallback(value, attempt, expected):
    assert _retry_after_seconds(value, attempt) == expected


def test_retry_after_seconds_http_date_clamped_to_ceiling():
    # A date far in the future clamps to the 600s ceiling rather than stalling.
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime

    far_future = format_datetime(datetime.now(timezone.utc) + timedelta(days=365))
    assert _retry_after_seconds(far_future, 0) == 600.0


def test_retry_after_seconds_http_date_in_the_past_is_clamped_to_zero():
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime

    past = format_datetime(datetime.now(timezone.utc) - timedelta(days=1))
    assert _retry_after_seconds(past, 0) == 0.0


def test_retry_after_seconds_never_raises_on_garbage_date():
    assert math.isfinite(_retry_after_seconds("Not, a, date, at, all", 0))
