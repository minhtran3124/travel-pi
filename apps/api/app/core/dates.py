"""Deterministic resolution of travel-date expressions: a numeric fast path (:func:`parse_numeric_date`) and arithmetic over a model-parsed :class:`~app.schemas.date_intent.DateIntent` (:func:`compute_from_intent`), anchored to the calendar week (Mon-Sun) and never guessing (raises :class:`AmbiguousDateError`)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.schemas.date_intent import DateIntent


class AmbiguousDateError(ValueError):
    """Raised when a date expression can't be resolved without guessing (subclasses :class:`ValueError` so existing ``except ValueError`` callers keep working)."""


# Reject absurd day offsets before they reach date arithmetic.
_MAX_DAY_OFFSET = 730


def _monday_of_week(day: date) -> date:
    """Return the Monday of the calendar week containing ``day``."""
    return day - timedelta(days=day.weekday())


def _next_occurrence_strictly_after(today: date, weekday: int) -> date:
    """Return the nearest date strictly after ``today`` matching ``weekday`` (Monday=0..Sunday=6)."""
    delta = (weekday - today.weekday()) % 7
    if delta == 0:
        delta = 7
    return today + timedelta(days=delta)


def parse_numeric_date(raw: str, today: date) -> str:
    """Parse a purely numeric date (ISO, ``DD/MM``, ``DD/MM/YYYY``, ``YYYY/MM/DD``) to ISO ``YYYY-MM-DD``; a missing year picks the nearest future occurrence, and non-numeric input raises :class:`AmbiguousDateError`."""
    if not raw or not raw.strip():
        raise ValueError("empty date")
    try:
        return _parse_numeric(raw.strip().lower(), today)
    except (OverflowError, OSError) as e:
        # Guard a huge literal overflowing C-level date math into a non-ValueError
        # that would escape the tool layer's ``except ValueError``.
        raise AmbiguousDateError(f"{raw!r} is out of range: {e}") from e


def _parse_numeric(token: str, today: date) -> str:
    """Do the numeric matching for :func:`parse_numeric_date`."""
    # 1. Already ISO — validate and pass through untouched.
    try:
        return datetime.strptime(token, "%Y-%m-%d").date().isoformat()
    except ValueError:
        pass

    # 2. Slash/dash numeric forms.
    parts = token.replace("-", "/").split("/")
    if len(parts) in (2, 3) and all(p.isdigit() and p != "" for p in parts):
        # 2a. YYYY/MM/DD — a common model slip on ISO; a 4-digit leading part is unambiguously a year.
        if len(parts) == 3 and len(parts[0]) == 4:
            return date(int(parts[0]), int(parts[1]), int(parts[2])).isoformat()
        # 2b. A 2-part token ending in a 4-digit year is a bare month/year with no day — never guess the day; raise.
        if len(parts) == 2 and len(parts[1]) == 4:
            raise AmbiguousDateError(
                f"{token!r} has no day component (bare month/year)"
            )
        # 2c. Day-first DD/MM/YYYY or DD/MM (year inferred).
        day, month = int(parts[0]), int(parts[1])
        if len(parts) == 3:
            year = int(parts[2])
            if year < 100:  # 2-digit year -> 20xx
                year += 2000
            return date(year, month, day).isoformat()  # raises ValueError if invalid
        # No year given: this year, or next year if that date already passed.
        try:
            candidate = date(today.year, month, day)
        except ValueError as e:
            raise ValueError(f"invalid date {token!r}") from e
        if candidate < today:
            candidate = date(today.year + 1, month, day)
        return candidate.isoformat()

    raise AmbiguousDateError(f"not a numeric date: {token!r}")


def compute_from_intent(intent: DateIntent, today: date) -> str:
    """Turn a model-parsed :class:`DateIntent` into an ISO ``YYYY-MM-DD`` date — pure arithmetic over untrusted input; a malformed intent raises :class:`AmbiguousDateError` rather than crashing."""
    try:
        return _compute(intent, today)
    except (OverflowError, OSError) as e:
        raise AmbiguousDateError(f"{intent!r} is out of range: {e}") from e


def _compute(intent: DateIntent, today: date) -> str:
    """Do the per-kind arithmetic for :func:`compute_from_intent`."""
    kind = intent.kind

    if kind == "absolute":
        if intent.month is None or intent.day is None:
            raise AmbiguousDateError("absolute intent missing month/day")
        if intent.year is not None:
            return date(intent.year, intent.month, intent.day).isoformat()
        # No year given: this year, or next year if that date already passed.
        try:
            candidate = date(today.year, intent.month, intent.day)
        except ValueError as e:
            raise ValueError(f"invalid date in intent: {e}") from e
        if candidate < today:
            candidate = date(today.year + 1, intent.month, intent.day)
        return candidate.isoformat()

    if kind in ("relative_day", "offset"):
        offset = intent.day_offset
        if offset is None or not (0 <= offset <= _MAX_DAY_OFFSET):
            raise AmbiguousDateError(f"day_offset out of range: {offset!r}")
        return (today + timedelta(days=offset)).isoformat()

    if kind == "weekday":
        weekday = intent.weekday
        if weekday is None or not (0 <= weekday <= 6):
            raise AmbiguousDateError(f"invalid weekday: {weekday!r}")
        if intent.week == "next":
            next_monday = _monday_of_week(today) + timedelta(days=7)
            return (next_monday + timedelta(days=weekday)).isoformat()
        if intent.week == "current":
            candidate = _monday_of_week(today) + timedelta(days=weekday)
            if candidate < today:
                raise AmbiguousDateError("weekday already passed this calendar week")
            return candidate.isoformat()
        if intent.week == "bare":
            return _next_occurrence_strictly_after(today, weekday).isoformat()
        raise AmbiguousDateError(f"invalid week for weekday intent: {intent.week!r}")

    if kind == "week_start":
        if intent.week == "next":
            return (_monday_of_week(today) + timedelta(days=7)).isoformat()
        if intent.week == "current":
            return _monday_of_week(today).isoformat()
        raise AmbiguousDateError(f"invalid week for week_start intent: {intent.week!r}")

    if kind == "weekend":
        if intent.week == "next":
            return (_monday_of_week(today) + timedelta(days=12)).isoformat()
        if intent.week == "current":
            if today.weekday() in (5, 6):  # Sat or Sun: this weekend is now.
                return today.isoformat()
            return (_monday_of_week(today) + timedelta(days=5)).isoformat()
        raise AmbiguousDateError(f"invalid week for weekend intent: {intent.week!r}")

    if kind == "ambiguous":
        raise AmbiguousDateError(intent.reason or "ambiguous date expression")

    raise AmbiguousDateError(f"unrecognized intent kind: {kind!r}")


def resolve_travel_date(raw: str, today: date) -> str:
    """Numeric-only alias of :func:`parse_numeric_date` (the search tools' backstop); word input raises :class:`AmbiguousDateError` so it fails loudly toward the LLM-backed parser."""
    return parse_numeric_date(raw, today)


def today_in_timezone(tz_name: str | None) -> date:
    """Return the current date in ``tz_name``, degrading to UTC on a missing/invalid IANA name rather than raising."""
    if tz_name:
        try:
            return datetime.now(ZoneInfo(tz_name)).date()
        except Exception:
            pass
    return datetime.now(timezone.utc).date()
