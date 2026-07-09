from datetime import date

import pytest
from app.core.dates import resolve_travel_date

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
    ],
)
def test_resolves_simple_forms(raw, expected):
    assert resolve_travel_date(raw, TODAY) == expected


@pytest.mark.parametrize(
    "raw", ["", "   ", "next friday", "someday", "07/2026", "99/99"]
)
def test_rejects_unresolvable(raw):
    with pytest.raises(ValueError):
        resolve_travel_date(raw, TODAY)
