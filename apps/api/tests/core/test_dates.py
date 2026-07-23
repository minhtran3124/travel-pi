from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from app.core.dates import (
    AmbiguousDateError,
    compute_from_intent,
    parse_numeric_date,
    resolve_travel_date,
    today_in_timezone,
)
from app.schemas.date_intent import DateIntent

TODAY = date(2026, 7, 9)  # a Thursday


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-07-10", "2026-07-10"),
        ("10/07/2026", "2026-07-10"),
        ("10-07-2026", "2026-07-10"),
        ("10/07", "2026-07-10"),
        ("08/07", "2027-07-08"),
        ("2026/07/10", "2026-07-10"),  # YYYY/MM/DD slash form (model slip on ISO)
    ],
)
def test_parse_numeric_date_resolves_numeric_forms(raw, expected):
    assert parse_numeric_date(raw, TODAY) == expected
    assert resolve_travel_date(raw, TODAY) == expected


def test_today_in_timezone_valid():
    assert (
        today_in_timezone("Asia/Ho_Chi_Minh")
        == datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    )


def test_today_in_timezone_invalid_falls_back_to_utc():
    # A misconfigured tz name must not raise — it degrades to UTC.
    assert today_in_timezone("Not/AZone") == datetime.now(timezone.utc).date()


def test_today_in_timezone_none_uses_utc():
    assert today_in_timezone(None) == datetime.now(timezone.utc).date()


@pytest.mark.parametrize("raw", ["", "   "])
def test_parse_numeric_date_rejects_empty(raw):
    with pytest.raises(ValueError):
        parse_numeric_date(raw, TODAY)


@pytest.mark.parametrize(
    "raw",
    [
        "someday",
        "gibberish date",
        "tomorrow",
        "friday",
        "next friday",
        "thứ 6 tuần sau",
    ],
)
def test_parse_numeric_date_rejects_words(raw):
    # The numeric fast path never matches a word — that's the LLM's job now.
    with pytest.raises(AmbiguousDateError):
        parse_numeric_date(raw, TODAY)


def test_invalid_calendar_date_raises_plain_valueerror():
    # "99/99" is just an invalid date (not ambiguous) -> a plain ValueError,
    # not the AmbiguousDateError subclass.
    with pytest.raises(ValueError) as exc_info:
        parse_numeric_date("99/99", TODAY)
    assert not isinstance(exc_info.value, AmbiguousDateError)


def test_bare_month_year_raises_ambiguous():
    with pytest.raises(AmbiguousDateError):
        parse_numeric_date("07/2026", TODAY)


def test_resolve_travel_date_is_numeric_only_alias():
    assert resolve_travel_date("2026-07-10", TODAY) == "2026-07-10"
    with pytest.raises(AmbiguousDateError):
        resolve_travel_date("tomorrow", TODAY)


# --- compute_from_intent -----------------------------------------------


def _intent(**kwargs) -> DateIntent:
    return DateIntent(**kwargs)


@pytest.mark.parametrize(
    "intent,expected",
    [
        # relative_day: today=0, tomorrow=1, day-after=2.
        (_intent(kind="relative_day", day_offset=0), "2026-07-09"),
        (_intent(kind="relative_day", day_offset=1), "2026-07-10"),
        (_intent(kind="relative_day", day_offset=2), "2026-07-11"),
        # Bare weekday -> next occurrence strictly after today (TODAY = Thu
        # 2026-07-09; the very next Friday is 07-10).
        (_intent(kind="weekday", weekday=4, week="bare"), "2026-07-10"),
        # Bare weekday equal to today's own weekday must roll to next week,
        # never resolve to today (TODAY is a Thursday, weekday=3).
        (_intent(kind="weekday", weekday=3, week="bare"), "2026-07-16"),
        # week="current" -> that weekday within the CURRENT calendar week
        # (Mon 07-06..Sun 07-12); Friday hasn't passed yet.
        (_intent(kind="weekday", weekday=4, week="current"), "2026-07-10"),
        # "current <today's own weekday>" resolves to today itself: it
        # hasn't passed "this week" — it IS this week, right now.
        (_intent(kind="weekday", weekday=3, week="current"), "2026-07-09"),
        # week="next" -> Monday-of-next-week + weekday offset (week-anchored
        # — NOT "strictly-future occurrence + 7 days", the P0 bug this
        # module fixes). Coincides with the bare case for a Thursday anchor
        # since Friday is the very next day; see the multi-anchor sweep
        # below for the case that exposes the bug.
        (_intent(kind="weekday", weekday=4, week="next"), "2026-07-17"),
        # Sunday.
        (_intent(kind="weekday", weekday=6, week="bare"), "2026-07-12"),
        # week_start.
        (_intent(kind="week_start", week="current"), "2026-07-06"),
        (_intent(kind="week_start", week="next"), "2026-07-13"),
        # weekend, current week: the coming Saturday.
        (_intent(kind="weekend", week="current"), "2026-07-11"),
        # weekend, next calendar week.
        (_intent(kind="weekend", week="next"), "2026-07-18"),
        # offset.
        (_intent(kind="offset", day_offset=3), "2026-07-12"),
        (_intent(kind="offset", day_offset=1), "2026-07-10"),
        # absolute, year given.
        (_intent(kind="absolute", year=2026, month=7, day=10), "2026-07-10"),
        # absolute, no year -> nearest future occurrence (07-08 already
        # passed this year, so 2027).
        (_intent(kind="absolute", month=7, day=8), "2027-07-08"),
        (_intent(kind="absolute", month=7, day=10), "2026-07-10"),
    ],
)
def test_compute_from_intent_resolves_forms(intent, expected):
    assert compute_from_intent(intent, TODAY) == expected


def test_compute_from_intent_current_weekday_already_passed_raises_ambiguous():
    # TODAY is Thursday 2026-07-09; Monday of this calendar week (07-06)
    # already passed. Asking beats silently rolling forward to next week.
    with pytest.raises(AmbiguousDateError):
        compute_from_intent(_intent(kind="weekday", weekday=0, week="current"), TODAY)


def test_compute_from_intent_ambiguous_kind_raises_with_reason():
    intent = _intent(kind="ambiguous", reason="traveller gave no date signal")
    with pytest.raises(AmbiguousDateError, match="traveller gave no date signal"):
        compute_from_intent(intent, TODAY)


@pytest.mark.parametrize(
    "intent",
    [
        # kind says weekday but weekday is None.
        _intent(kind="weekday", week="bare"),
        # kind says weekday but week is missing.
        _intent(kind="weekday", weekday=4),
        # kind says absolute but month/day missing.
        _intent(kind="absolute", year=2026),
        # kind says relative_day but day_offset missing.
        _intent(kind="relative_day"),
        # kind says week_start but week missing.
        _intent(kind="week_start"),
        # kind says weekend but week missing.
        _intent(kind="weekend"),
    ],
)
def test_compute_from_intent_malformed_raises_ambiguous_not_crash(intent):
    with pytest.raises(AmbiguousDateError):
        compute_from_intent(intent, TODAY)


# The 7 possible anchor weekdays for TODAY, Mon 2026-07-06..Sun 2026-07-12.
# The original P0 bug ("next"-prefixed weekday overshoots by 7 days) is
# invisible when the anchor happens to be a Thursday — every case above
# pins TODAY there — so the regression tests below sweep every anchor.
_WEEK_ANCHORS = [date(2026, 7, 6) + timedelta(days=i) for i in range(7)]


@pytest.mark.parametrize("anchor", _WEEK_ANCHORS, ids=lambda d: d.strftime("%A"))
def test_next_weekday_never_overshoots_next_week_window(anchor):
    # weekday+week="next" must always land inside the 7-day window that
    # week_start+week="next" opens — never Monday + 7 extra.
    next_week_monday = date.fromisoformat(
        compute_from_intent(_intent(kind="week_start", week="next"), anchor)
    )
    next_friday = date.fromisoformat(
        compute_from_intent(_intent(kind="weekday", weekday=4, week="next"), anchor)
    )
    assert next_friday == next_week_monday + timedelta(days=4)
    assert next_week_monday <= next_friday <= next_week_monday + timedelta(days=6)


def test_next_weekday_matches_confirmed_bug_report_example():
    # Exact figures from the confirmed P0 finding (today = Sat 2026-07-11).
    today = date(2026, 7, 11)
    assert (
        compute_from_intent(_intent(kind="week_start", week="next"), today)
        == "2026-07-13"
    )
    assert (
        compute_from_intent(_intent(kind="weekday", weekday=0, week="next"), today)
        == "2026-07-13"
    )
    assert (
        compute_from_intent(_intent(kind="weekday", weekday=4, week="next"), today)
        == "2026-07-17"
    )


@pytest.mark.parametrize("anchor", _WEEK_ANCHORS, ids=lambda d: d.strftime("%A"))
def test_weekend_current_is_that_weeks_saturday_or_today(anchor):
    resolved = date.fromisoformat(
        compute_from_intent(_intent(kind="weekend", week="current"), anchor)
    )
    if anchor.weekday() in (5, 6):  # Sat/Sun: the weekend is already now.
        assert resolved == anchor
    else:
        assert resolved == date(2026, 7, 11)  # Saturday of that same week.


def test_weekend_next_is_saturday_of_next_week():
    assert (
        compute_from_intent(_intent(kind="weekend", week="next"), TODAY) == "2026-07-18"
    )


@pytest.mark.parametrize("day_offset", [-1, 731, 3_000_000])
def test_offset_outside_window_raises_ambiguous(day_offset):
    with pytest.raises(AmbiguousDateError):
        compute_from_intent(_intent(kind="offset", day_offset=day_offset), TODAY)
    with pytest.raises(AmbiguousDateError):
        compute_from_intent(_intent(kind="relative_day", day_offset=day_offset), TODAY)


def test_offset_at_max_window_resolves():
    assert (
        compute_from_intent(_intent(kind="offset", day_offset=730), TODAY)
        == (TODAY + timedelta(days=730)).isoformat()
    )


def test_unrecognized_kind_raises_ambiguous_not_crash():
    # Pydantic's Literal validation would normally reject this at
    # construction, but guard the arithmetic layer too in case a caller
    # bypasses the schema (e.g. constructs via model_construct).
    intent = DateIntent.model_construct(kind="bogus")
    with pytest.raises(AmbiguousDateError):
        compute_from_intent(intent, TODAY)
