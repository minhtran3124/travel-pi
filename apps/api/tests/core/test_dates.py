from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from app.core.dates import AmbiguousDateError, resolve_travel_date, today_in_timezone

TODAY = date(2026, 7, 9)  # a Thursday


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-07-10", "2026-07-10"),
        ("today", "2026-07-09"),
        ("hôm nay", "2026-07-09"),
        ("tomorrow", "2026-07-10"),
        ("ngày mai", "2026-07-10"),
        ("Ngày Mai", "2026-07-10"),
        ("mai", "2026-07-10"),
        ("ngày kia", "2026-07-11"),
        ("10/07/2026", "2026-07-10"),
        ("10-07-2026", "2026-07-10"),
        ("10/07", "2026-07-10"),
        ("08/07", "2027-07-08"),
        ("2026/07/10", "2026-07-10"),  # YYYY/MM/DD slash form (model slip on ISO)
    ],
)
def test_resolves_simple_forms(raw, expected):
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


@pytest.mark.parametrize("raw", ["", "   ", "someday"])
def test_rejects_unresolvable(raw):
    with pytest.raises(ValueError):
        resolve_travel_date(raw, TODAY)


@pytest.mark.parametrize("raw", ["someday", "gibberish date"])
def test_unrecognized_phrase_raises_ambiguous(raw):
    with pytest.raises(AmbiguousDateError):
        resolve_travel_date(raw, TODAY)


def test_invalid_calendar_date_raises_plain_valueerror():
    # "99/99" is just an invalid date (not ambiguous) -> a plain ValueError,
    # not the AmbiguousDateError subclass.
    with pytest.raises(ValueError) as exc_info:
        resolve_travel_date("99/99", TODAY)
    assert not isinstance(exc_info.value, AmbiguousDateError)


def test_bare_month_year_raises_ambiguous():
    with pytest.raises(AmbiguousDateError):
        resolve_travel_date("07/2026", TODAY)


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Bare weekday -> next occurrence strictly after today (TODAY = Thu
        # 2026-07-09; the very next Friday is 07-10). Unchanged by the P0 fix.
        ("friday", "2026-07-10"),
        ("Friday", "2026-07-10"),
        ("thứ 6", "2026-07-10"),
        ("thu 6", "2026-07-10"),
        ("t6", "2026-07-10"),
        ("thứ Sáu", "2026-07-10"),
        ("thu sau", "2026-07-10"),
        # Bare weekday equal to today's own weekday must roll to next week,
        # never resolve to today (TODAY is a Thursday).
        ("thursday", "2026-07-16"),
        ("thứ 5", "2026-07-16"),
        # "this"-prefixed weekday -> that weekday within the CURRENT
        # calendar week (Mon 07-06..Sun 07-12); Friday hasn't passed yet.
        ("this friday", "2026-07-10"),
        ("thứ 6 tuần này", "2026-07-10"),
        # "this <today's own weekday>" resolves to today itself: it hasn't
        # passed "this week" — it IS this week, right now.
        ("this thursday", "2026-07-09"),
        # "next"-prefixed weekday -> Monday-of-next-week + weekday offset
        # (week-anchored — NOT "strictly-future occurrence + 7 days", the
        # P0 bug this fix corrects). These two coincide for a Thursday
        # anchor since Friday is the very next day; see the dedicated
        # multi-anchor regression tests below for the case that exposes
        # the bug.
        ("next friday", "2026-07-17"),
        ("thứ 6 tuần sau", "2026-07-17"),
        ("thu 6 tuan sau", "2026-07-17"),
        # Sunday shorthand.
        ("chủ nhật", "2026-07-12"),
        ("chu nhat", "2026-07-12"),
        ("cn", "2026-07-12"),
        ("sunday", "2026-07-12"),
        # "next week" / "tuần sau" -> Monday of next calendar week.
        ("next week", "2026-07-13"),
        ("tuần sau", "2026-07-13"),
        ("tuan sau", "2026-07-13"),
        # "this weekend" / "cuối tuần này" -> the coming Saturday.
        ("this weekend", "2026-07-11"),
        ("cuối tuần này", "2026-07-11"),
        ("cuoi tuan nay", "2026-07-11"),
        # "next weekend" / "cuối tuần sau" -> Saturday of NEXT calendar
        # week. Previously unimplemented (raised AmbiguousDateError) even
        # though the resolve_date tool docstring already advertised it.
        ("next weekend", "2026-07-18"),
        ("cuối tuần sau", "2026-07-18"),
        ("cuoi tuan sau", "2026-07-18"),
        # Day offsets.
        ("in 3 days", "2026-07-12"),
        ("in 1 day", "2026-07-10"),
        ("3 ngày nữa", "2026-07-12"),
        ("3 ngay nua", "2026-07-12"),
    ],
)
def test_resolves_weekday_and_phrase_forms(raw, expected):
    assert resolve_travel_date(raw, TODAY) == expected


def test_this_weekday_already_passed_raises_ambiguous():
    # TODAY is Thursday 2026-07-09; Monday of this calendar week (07-06)
    # already passed. Asking beats silently rolling forward to next week.
    with pytest.raises(AmbiguousDateError):
        resolve_travel_date("this monday", TODAY)
    with pytest.raises(AmbiguousDateError):
        resolve_travel_date("thứ 2 tuần này", TODAY)


# The 7 possible anchor weekdays for TODAY, Mon 2026-07-06..Sun 2026-07-12.
# The original P0 bug ("next"-prefixed weekday overshoots by 7 days) is
# invisible when the anchor happens to be a Thursday — every case above
# pins TODAY there — so the regression tests below sweep every anchor.
_WEEK_ANCHORS = [date(2026, 7, 6) + timedelta(days=i) for i in range(7)]


@pytest.mark.parametrize("anchor", _WEEK_ANCHORS, ids=lambda d: d.strftime("%A"))
def test_next_weekday_never_overshoots_next_week_window(anchor):
    # "<weekday> tuần sau" must always land inside the 7-day window that
    # starts at "tuần sau" (Monday of next week) — never Monday + 7 extra.
    next_week_monday = date.fromisoformat(resolve_travel_date("tuần sau", anchor))
    next_friday = date.fromisoformat(resolve_travel_date("thứ 6 tuần sau", anchor))
    assert next_friday == next_week_monday + timedelta(days=4)
    assert next_week_monday <= next_friday <= next_week_monday + timedelta(days=6)


_NEXT_WEEK_SYNONYMS = ["tuần sau", "tuần tới", "tuần kế", "tuần tiếp theo"]


@pytest.mark.parametrize("anchor", _WEEK_ANCHORS, ids=lambda d: d.strftime("%A"))
def test_next_week_synonyms_resolve_identically(anchor):
    # A traveller picks whichever spelling they please — "thứ 2 tuần tới" is as
    # common as "thứ 2 tuần sau". Every synonym must land on the same day, or the
    # unmatched ones raise AmbiguousDateError and the agent asks a needless
    # question about a phrase that was never ambiguous (reported from the chat UI).
    bare = {resolve_travel_date(s, anchor) for s in _NEXT_WEEK_SYNONYMS}
    assert len(bare) == 1
    assert resolve_travel_date("sang tuần", anchor) == bare.pop()

    with_weekday = {
        resolve_travel_date(f"thứ 2 {s}", anchor) for s in _NEXT_WEEK_SYNONYMS
    }
    assert with_weekday == {
        resolve_travel_date("tuần sau", anchor)
    }  # Monday of next week

    weekend = {
        resolve_travel_date(s, anchor) for s in ("cuối tuần sau", "cuối tuần tới")
    }
    assert len(weekend) == 1


def test_next_weekday_matches_confirmed_bug_report_example():
    # Exact figures from the confirmed P0 finding (today = Sat 2026-07-11).
    today = date(2026, 7, 11)
    assert resolve_travel_date("tuần sau", today) == "2026-07-13"
    assert resolve_travel_date("thứ 2 tuần sau", today) == "2026-07-13"
    assert resolve_travel_date("thứ 6 tuần sau", today) == "2026-07-17"


@pytest.mark.parametrize("anchor", _WEEK_ANCHORS, ids=lambda d: d.strftime("%A"))
def test_this_weekend_is_current_week_saturday_or_today(anchor):
    resolved = date.fromisoformat(resolve_travel_date("this weekend", anchor))
    if anchor.weekday() in (5, 6):  # Sat/Sun: the weekend is already now.
        assert resolved == anchor
    else:
        assert resolved == date(2026, 7, 11)  # Saturday of that same week.


def test_next_weekend_is_saturday_of_next_week():
    assert resolve_travel_date("next weekend", TODAY) == "2026-07-18"
    assert resolve_travel_date("cuối tuần sau", TODAY) == "2026-07-18"
    assert resolve_travel_date("cuoi tuan sau", TODAY) == "2026-07-18"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("friday!", "2026-07-10"),
        ("thứ 6.", "2026-07-10"),
        ("hôm  nay", "2026-07-09"),
        ("  Friday  ", "2026-07-10"),
        ("next friday?", "2026-07-17"),
    ],
)
def test_punctuation_and_whitespace_noise_does_not_block_resolution(raw, expected):
    assert resolve_travel_date(raw, TODAY) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "in 99999999999999999999999999 days",
        "3000000 ngày nữa",
        "in 731 days",
    ],
)
def test_day_offset_outside_window_raises_ambiguous_not_overflow(raw):
    # OverflowError (not ValueError) must never escape this function —
    # every caller in the tool layer only catches ValueError/AmbiguousDateError.
    with pytest.raises(AmbiguousDateError):
        resolve_travel_date(raw, TODAY)


def test_day_offset_at_max_window_resolves():
    assert (
        resolve_travel_date("in 730 days", TODAY)
        == (TODAY + timedelta(days=730)).isoformat()
    )
