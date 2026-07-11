"""Deterministic resolution of travel-date expressions.

This module owns two language-independent halves. Understanding a
traveller's phrasing ("next Friday", "cuối tuần này", 来週の月曜日) is a job
for the ``date_resolution`` LLM (see ``app/tools/date_tools.py``); date
arithmetic is not — a model can misjudge language, but it should never be
trusted to add days in its head. So:

- :func:`parse_numeric_date` is the zero-token fast path: pure numeric forms
  (ISO, ``DD/MM``, ``DD/MM/YYYY``, ``YYYY/MM/DD``) that never need a model
  call. No word is ever matched here.
- :func:`compute_from_intent` takes a :class:`~app.schemas.date_intent.DateIntent`
  — the *parsed* shape the model returns, never a date the model computed —
  and turns it into an ISO date deterministically.

Both raise :class:`AmbiguousDateError` (a :class:`ValueError` subclass)
rather than guess. Weekday/week semantics (pinned, not just "a sensible
convention"), anchored to the **calendar week (Monday-Sunday)**:

- A **bare** weekday (``week="bare"``) resolves to the next occurrence of
  that weekday **strictly after** today — never today itself, never the past.
- A **current-week** weekday (``week="current"``) resolves to that weekday
  **within the current calendar week**. If it already passed, that's a guess
  (roll to next week? report an error?) — raises :class:`AmbiguousDateError`
  instead of picking one.
- A **next-week** weekday (``week="next"``) resolves to that weekday
  **within the next calendar week** — i.e. Monday-of-next-week plus the
  weekday offset. This intentionally lands inside the same 7-day window as
  ``week_start`` with ``week="next"``.
- ``week_start`` -> the Monday of the current/next calendar week.
- ``weekend`` with ``week="current"`` -> the Saturday of the current
  calendar week — or **today**, if today already is that Saturday or the
  following Sunday (the weekend is already underway). With ``week="next"``
  -> the Saturday of next calendar week.
- ``relative_day`` / ``offset`` -> today plus a day count, bounded to
  0..730 days; outside that window, or missing, raises
  :class:`AmbiguousDateError`.
- ``absolute`` -> that calendar date; a null year picks the nearest future
  occurrence of that day/month.
- ``ambiguous`` -> raises :class:`AmbiguousDateError` carrying the model's
  reason.
- A malformed intent (a kind whose required fields are missing/out of
  range) raises :class:`AmbiguousDateError` rather than crashing — the model
  fills this field, so it is untrusted input.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.schemas.date_intent import DateIntent


class AmbiguousDateError(ValueError):
    """Raised when a date expression cannot be resolved without guessing.

    Subclasses :class:`ValueError` so existing ``except ValueError`` callers
    (``flight_tools``, ``hotel_tools``) keep working unchanged; callers that
    want to route ambiguity to a traveller-facing question can catch this
    type specifically.
    """


# Reject day offsets outside a sane travel-planning window rather than
# letting an absurd offset reach ``timedelta``/``date`` arithmetic.
_MAX_DAY_OFFSET = 730


def _monday_of_week(day: date) -> date:
    """Return the Monday of the calendar week containing ``day``.

    :param day: Any date.
    :return: The Monday on/before ``day``.
    """
    return day - timedelta(days=day.weekday())


def _next_occurrence_strictly_after(today: date, weekday: int) -> date:
    """Return the next date on/after ``today`` matching ``weekday``, excluding today.

    :param today: The date to search forward from (not included in the result).
    :param weekday: Target ``Monday=0..Sunday=6`` index.
    :return: The nearest matching date strictly after ``today``.
    """
    delta = (weekday - today.weekday()) % 7
    if delta == 0:
        delta = 7
    return today + timedelta(days=delta)


def parse_numeric_date(raw: str, today: date) -> str:
    """Parse a purely numeric date expression to ISO ``YYYY-MM-DD``.

    The zero-token fast path: handles ISO dates (validated, returned
    unchanged — deliberately does not reject a past date), day-first
    ``DD/MM`` or ``DD/MM/YYYY`` (a missing year picks the nearest future
    occurrence; a 2-digit year is read as 20xx), and ``YYYY/MM/DD`` (a
    common model slip on the ISO format). No word is ever matched — a
    non-numeric expression raises :class:`AmbiguousDateError` so the caller
    can fall back to the ``date_resolution`` LLM.

    :param raw: The traveller-supplied date token.
    :param today: The current date in the traveller's timezone (grounds a
        missing year).
    :returns: An ISO ``YYYY-MM-DD`` date string.
    :raises AmbiguousDateError: If ``raw`` is not a numeric date, or is a
        bare month/year with no day component.
    :raises ValueError: If ``raw`` is empty or names an invalid calendar date.
    """
    if not raw or not raw.strip():
        raise ValueError("empty date")
    try:
        return _parse_numeric(raw.strip().lower(), today)
    except (OverflowError, OSError) as e:
        # Belt-and-braces: guards against a huge numeric literal overflowing
        # C-level date arithmetic in a way that isn't a plain ValueError,
        # which would escape every ``except ValueError`` in the tool layer.
        raise AmbiguousDateError(f"{raw!r} is out of range: {e}") from e


def _parse_numeric(token: str, today: date) -> str:
    """Do the actual numeric matching for :func:`parse_numeric_date`.

    :param token: The lowercased, stripped date token.
    :param today: The current date in the traveller's timezone.
    :returns: An ISO ``YYYY-MM-DD`` date string.
    :raises AmbiguousDateError: See :func:`parse_numeric_date`.
    :raises ValueError: See :func:`parse_numeric_date`.
    """
    # 1. Already ISO — validate and pass through untouched.
    try:
        return datetime.strptime(token, "%Y-%m-%d").date().isoformat()
    except ValueError:
        pass

    # 2. Slash/dash numeric forms.
    parts = token.replace("-", "/").split("/")
    if len(parts) in (2, 3) and all(p.isdigit() and p != "" for p in parts):
        # 2a. YYYY/MM/DD — a common model slip on the ISO format (dashes
        # expected). A 4-digit leading part is unambiguously a year.
        if len(parts) == 3 and len(parts[0]) == 4:
            return date(int(parts[0]), int(parts[1]), int(parts[2])).isoformat()
        # 2b. A 2-part token whose second half is a 4-digit year (e.g.
        # "07/2026") is a bare month/year with no day — equally readable as
        # DD/MM (day 7, "month" 2026: invalid) or MM/YYYY with no day given.
        # Never guess which day of the month; raise instead.
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
    """Turn a model-parsed :class:`DateIntent` into an ISO ``YYYY-MM-DD`` date.

    Pure arithmetic — never guesses. ``intent`` is untrusted input (an LLM
    fills it), so a malformed combination of fields raises
    :class:`AmbiguousDateError` rather than crashing.

    :param intent: The structured intent returned by the ``date_resolution``
        model.
    :param today: The current date in the traveller's timezone.
    :returns: An ISO ``YYYY-MM-DD`` date string.
    :raises AmbiguousDateError: If ``intent`` is ambiguous, malformed, or
        resolves outside the supported range (see the module docstring for
        the full semantics table).
    :raises ValueError: If ``intent`` names an invalid calendar date.
    """
    try:
        return _compute(intent, today)
    except (OverflowError, OSError) as e:
        raise AmbiguousDateError(f"{intent!r} is out of range: {e}") from e


def _compute(intent: DateIntent, today: date) -> str:
    """Do the actual per-kind arithmetic for :func:`compute_from_intent`.

    :param intent: The structured intent returned by the model.
    :param today: The current date in the traveller's timezone.
    :returns: An ISO ``YYYY-MM-DD`` date string.
    :raises AmbiguousDateError: See :func:`compute_from_intent`.
    :raises ValueError: See :func:`compute_from_intent`.
    """
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
    """Numeric-only alias of :func:`parse_numeric_date`.

    Kept for the search tools' backstop (``flight_tools``/``hotel_tools``
    call this by name), which only ever needs to validate an already-numeric
    date. Word input now raises :class:`AmbiguousDateError` here — an
    intentional tightening: a search tool receiving a word expression should
    fail loudly toward ``resolve_date`` (the LLM-backed parser in
    ``app/tools/date_tools.py``) rather than silently resolve it.

    :param raw: The traveller-supplied date token.
    :param today: The current date in the traveller's timezone.
    :returns: An ISO ``YYYY-MM-DD`` date string.
    :raises AmbiguousDateError: See :func:`parse_numeric_date`.
    :raises ValueError: See :func:`parse_numeric_date`.
    """
    return parse_numeric_date(raw, today)


def today_in_timezone(tz_name: str | None) -> date:
    """Return the current date in ``tz_name``, falling back to UTC on a bad name.

    Used by tools to ground "today" without crashing on a misconfigured
    ``AGENT_TIMEZONE`` — an invalid IANA name degrades to UTC rather than raising
    ``ZoneInfoNotFoundError`` out of the tool.

    :param tz_name: An IANA timezone name, or None (→ UTC).
    :return: Today's date in that zone (UTC if the name is missing/invalid).
    """
    if tz_name:
        try:
            return datetime.now(ZoneInfo(tz_name)).date()
        except Exception:
            pass
    return datetime.now(timezone.utc).date()
