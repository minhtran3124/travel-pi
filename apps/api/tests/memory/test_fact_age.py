"""Fact age (specs/agent-memory-layer-5 Task 1.1, SC-2).

Two properties are pinned here:

1. A stored ``updated_at`` survives round-trip through typed search
   (:func:`search_memory_typed`), so a caller can tell a fresh fact from a stale one.
2. :func:`format_age` renders that timestamp as a **month-granularity** bucket, returns
   ``None`` for missing/unparseable input (never a guess), and — critically — never emits
   a day-count phrase. The preferences/instructions blocks sit *before* ``summary`` in the
   cached system-prompt prefix (implicit caching, measured at 71.9%); a string that changed
   daily would invalidate that prefix for every user at each day rollover.
"""

from datetime import datetime, timedelta, timezone


def test_typed_search_carries_updated_at():
    """A preference's updated_at reaches the typed dataclass, parseable as ISO-8601."""
    from app.memory.store import get_store, search_memory_typed, upsert_preference

    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u1", "diet", {"text": "vegetarian"})

    prefs = search_memory_typed(store, "u1", "prefs")
    assert len(prefs) == 1
    assert prefs[0].updated_at is not None
    datetime.fromisoformat(prefs[0].updated_at)


def test_typed_search_updated_at_none_for_legacy_record():
    """A record written before stamping (no updated_at key) yields updated_at=None."""
    from app.memory.store import _prefs_namespace, get_store, search_memory_typed

    store = get_store("sqlite:///:memory:")
    store.put(_prefs_namespace("u1"), "legacy", {"text": "legacy pref"})

    prefs = search_memory_typed(store, "u1", "prefs")
    assert len(prefs) == 1
    assert prefs[0].updated_at is None


def test_typed_search_carries_updated_at_all_kinds():
    """updated_at rides through the typed dataclass for all three kinds."""
    from app.memory.store import (
        get_store,
        search_memory_typed,
        upsert_episode,
        upsert_instruction,
        upsert_preference,
    )

    store = get_store("sqlite:///:memory:")
    upsert_preference(store, "u", "diet", {"text": "veg"})
    upsert_instruction(store, "u", "cur", {"text": "EUR"})
    upsert_episode(store, "u", "t1", {"text": "Da Nang", "city": "Da Nang"})

    for kind in ("prefs", "procedural", "episodes"):
        rows = search_memory_typed(store, "u", kind)
        assert rows[0].updated_at is not None
        datetime.fromisoformat(rows[0].updated_at)


# --- format_age -------------------------------------------------------------

_NOW = datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)


def test_format_age_none_for_none():
    from app.memory.store import format_age

    assert format_age(None, now=_NOW) is None


def test_format_age_none_for_empty():
    from app.memory.store import format_age

    assert format_age("", now=_NOW) is None


def test_format_age_none_for_garbage():
    from app.memory.store import format_age

    assert format_age("not-a-date", now=_NOW) is None
    assert format_age("2026-13-99", now=_NOW) is None


def test_format_age_this_month():
    """Under one month old -> 'in the last month'."""
    from app.memory.store import format_age

    same_day = _NOW.isoformat()
    a_week = (_NOW - timedelta(days=7)).isoformat()
    just_under_month = (_NOW - timedelta(days=20)).isoformat()

    assert format_age(same_day, now=_NOW) == "in the last month"
    assert format_age(a_week, now=_NOW) == "in the last month"
    assert format_age(just_under_month, now=_NOW) == "in the last month"


def test_format_age_a_few_months():
    """One to just under twelve months -> 'a few months ago'."""
    from app.memory.store import format_age

    two_months = (_NOW - timedelta(days=65)).isoformat()
    six_months = (_NOW - timedelta(days=185)).isoformat()
    eleven_months = (_NOW - timedelta(days=340)).isoformat()

    assert format_age(two_months, now=_NOW) == "a few months ago"
    assert format_age(six_months, now=_NOW) == "a few months ago"
    assert format_age(eleven_months, now=_NOW) == "a few months ago"


def test_format_age_over_a_year():
    """Twelve months or more -> 'over a year ago'."""
    from app.memory.store import format_age

    thirteen_months = (_NOW - timedelta(days=400)).isoformat()
    three_years = (_NOW - timedelta(days=365 * 3)).isoformat()

    assert format_age(thirteen_months, now=_NOW) == "over a year ago"
    assert format_age(three_years, now=_NOW) == "over a year ago"


def test_format_age_boundary_one_month():
    """The <1-month / a-few-months boundary is crisp and month-granular."""
    from app.memory.store import format_age

    # Exactly one calendar month back reads as 'a few months ago', not 'in the last month'.
    one_month = datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    assert format_age(one_month, now=_NOW) == "a few months ago"


def test_format_age_never_emits_day_count_vocabulary():
    """CRITICAL cache constraint: no rendered age may contain a day-granularity word.

    A string that changes daily inside the cached system-prompt prefix would blow the
    71.9% hit rate at each day rollover, so assert the vocabulary is never produced —
    across a full year of daily offsets.
    """
    from app.memory.store import format_age

    banned = ("today", "yesterday", "day", "days", "week", "weeks", "hour", "minute")
    for days_back in range(0, 800):
        stamp = (_NOW - timedelta(days=days_back)).isoformat()
        rendered = format_age(stamp, now=_NOW)
        assert rendered is not None
        low = rendered.lower()
        for word in banned:
            assert word not in low, (
                f"day-count vocab {word!r} in {rendered!r} at -{days_back}d"
            )


def test_format_age_defaults_now_to_utc_now_without_raising():
    """Omitting now must not raise and must still bucket a recent stamp as 'in the last month'."""
    from app.memory.store import format_age

    recent = datetime.now(timezone.utc).isoformat()
    assert format_age(recent) == "in the last month"


def test_format_age_handles_naive_timestamp():
    """A timezone-naive ISO stamp is tolerated (treated as UTC), not a crash -> None."""
    from app.memory.store import format_age

    naive = datetime(2026, 9, 10, 12, 0, 0).isoformat()  # no tzinfo
    assert format_age(naive, now=_NOW) == "in the last month"


# --- Regressions found by correctness review (M2, M3) ------------------------


def test_freshest_phrase_does_not_claim_a_calendar_month():
    """M2: the code measures ELAPSED months, so the label must not say "this month".

    Read on 16 Sep, a row stamped 20 Aug scores 0 elapsed months but belongs to the
    *previous* calendar month. "this month" would be a false claim, wrong by up to
    nearly two calendar months; "in the last month" is true for the whole bucket and
    has identical prompt-cache properties.
    """
    from app.memory.store import _AGE_COARSE, _AGE_FINE, format_age

    late_last_month = datetime(2026, 8, 20, tzinfo=timezone.utc).isoformat()
    assert format_age(late_last_month, now=_NOW) == "in the last month"

    phrases = [p for _, p in _AGE_COARSE] + [p for _, p in _AGE_FINE]
    assert "this month" not in phrases


def test_future_timestamp_renders_no_age_at_all():
    """M3: an impossible stamp must not be shown as the freshest possible data.

    Clock skew, a bad backfill or a hand-edited row previously clamped to 0 months and
    rendered as the most confidence-inspiring label available. Unusable data renders as
    absent, matching the plan's constraint for a missing stamp.
    """
    from app.memory.store import format_age

    far_future = datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
    next_month = datetime(2026, 10, 20, tzinfo=timezone.utc).isoformat()

    assert format_age(far_future, now=_NOW) is None
    assert format_age(next_month, now=_NOW) is None
    assert format_age(far_future, now=_NOW, fine=True) is None
