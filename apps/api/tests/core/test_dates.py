from datetime import date, datetime, timezone
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
        # Bare / "this"-prefixed weekday -> next occurrence strictly after
        # today (TODAY = Thu 2026-07-09; the very next Friday is 07-10).
        ("friday", "2026-07-10"),
        ("Friday", "2026-07-10"),
        ("this friday", "2026-07-10"),
        ("thứ 6", "2026-07-10"),
        ("thu 6", "2026-07-10"),
        ("t6", "2026-07-10"),
        ("thứ 6 tuần này", "2026-07-10"),
        ("thứ Sáu", "2026-07-10"),
        ("thu sau", "2026-07-10"),
        # Bare weekday equal to today's own weekday must roll to next week,
        # never resolve to today (TODAY is a Thursday).
        ("thursday", "2026-07-16"),
        ("thứ 5", "2026-07-16"),
        # "next"-prefixed weekday -> the strictly-future occurrence + 7 days.
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
        # Day offsets.
        ("in 3 days", "2026-07-12"),
        ("in 1 day", "2026-07-10"),
        ("3 ngày nữa", "2026-07-12"),
        ("3 ngay nua", "2026-07-12"),
    ],
)
def test_resolves_weekday_and_phrase_forms(raw, expected):
    assert resolve_travel_date(raw, TODAY) == expected
