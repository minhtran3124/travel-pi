"""Deterministic resolution of the relative/weekday/partial travel-date forms.

A safety net beneath the LLM: rather than trusting the model to do date
arithmetic in its head ("next Friday", "cuối tuần này"), the agent sends the
traveller's literal expression through :func:`resolve_travel_date` and passes
the resulting ISO date to a tool. This module owns every form travellers
commonly type, so the LLM never has to compute a date itself.

Weekday/phrase semantics (pinned, not just "a sensible convention" — see
:class:`AmbiguousDateError` for the alternative), all anchored to the
**calendar week (Monday–Sunday)** so every form agrees with every other:

- A **bare** weekday ("friday", "thứ 6") resolves to the next occurrence of
  that weekday **strictly after** ``today`` — never today itself, never the
  past.
- A **"this"-prefixed** weekday ("this friday", "thứ 6 tuần này") resolves to
  that weekday **within the current calendar week**. If it has already
  passed this week, that's a guess (roll to next week? report an error?) —
  raise :class:`AmbiguousDateError` instead of picking one.
- A **"next"-prefixed** weekday ("next friday", "thứ 6 tuần sau") resolves to
  that weekday **within the next calendar week** — i.e. Monday-of-next-week
  plus the weekday offset. This intentionally lands inside the same 7-day
  window as the bare "next week"/"tuần sau" phrase below, so
  ``resolve("thứ 6 tuần sau")`` always falls within
  ``[resolve("tuần sau"), resolve("tuần sau") + 6 days]``.
- "next week" / "tuần sau" (bare, no weekday) -> the Monday of next calendar
  week.
- "this weekend" / "cuối tuần này" -> the Saturday of the current calendar
  week — or **today**, if today already is that Saturday or the following
  Sunday (the weekend "this week" refers to is already underway).
- "next weekend" / "cuối tuần sau" -> the Saturday of next calendar week.
- Nothing that would require guessing resolves at all — nothing this module
  can't parse, or a bare month/year with no day, raises
  :class:`AmbiguousDateError` instead.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.text import fold_diacritics


class AmbiguousDateError(ValueError):
    """Raised when a date expression cannot be resolved without guessing.

    Subclasses :class:`ValueError` so existing ``except ValueError`` callers
    (``flight_tools``, ``hotel_tools``) keep working unchanged; callers that
    want to route ambiguity to a traveller-facing question can catch this
    type specifically.
    """


# Relative day-words -> offset. Keys are diacritic-folded (see ``_normalize``,
# applied to every token before lookup), so a single ASCII key matches both
# accented ("hôm nay") and unaccented ("hom nay") traveller input.
_RELATIVE_DAYS: dict[str, int] = {
    "today": 0,
    "hom nay": 0,
    "tomorrow": 1,
    "ngay mai": 1,
    "mai": 1,
    "day after tomorrow": 2,
    "ngay kia": 2,
    "mot": 2,
}

# Weekday names (English + Vietnamese, diacritics already folded — see
# ``_normalize``) -> Python's Monday=0..Sunday=6.
_WEEKDAY_NAMES: dict[str, int] = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
    "thu hai": 0,
    "thu ba": 1,
    "thu tu": 2,
    "thu nam": 3,
    "thu sau": 4,
    "thu bay": 5,
    "chu nhat": 6,
}
_SUNDAY_SHORTHAND = "cn"

# VN numeric shorthand: "thứ 2".."thứ 7" / "thu 2".."thu 7" / "t2".."t7" ->
# Monday(0)..Saturday(5) (Vietnamese numbers weekdays from Monday=2; Sunday
# has no number, it's "Chủ Nhật"/"cn").
_VN_NUMERIC_WEEKDAY_RE = re.compile(r"^t(?:hu)?\s*([2-7])$")

_NEXT_PREFIX = "next "
_THIS_PREFIX = "this "
_NEXT_WEEK_SUFFIX = " tuan sau"
_THIS_WEEK_SUFFIX = " tuan nay"

_DAY_OFFSET_EN_RE = re.compile(r"^in (\d+) days?$")
_DAY_OFFSET_VN_RE = re.compile(r"^(\d+) ngay nua$")

# Reject day offsets outside a sane travel-planning window rather than
# letting an absurd offset ("in 99999999999999999999999999 days") reach
# ``timedelta``/``date`` arithmetic, where it raises ``OverflowError`` —
# not a ``ValueError``, so it would escape every ``except ValueError`` in
# the tool layer (``date_tools``, ``flight_tools``, ``hotel_tools``).
_MAX_DAY_OFFSET = 730

# Non-word characters (incl. punctuation) at the very start/end of a token,
# e.g. the trailing "!" in "friday!" or "." in "thứ 6.". Anchored, so it
# never touches meaningful *internal* separators like the "/" in "10/07".
_EDGE_NOISE_RE = re.compile(r"^[^\w]+|[^\w]+$", re.UNICODE)


def _normalize(raw: str) -> str:
    """Normalize a raw token once, up front, for every branch below.

    Lowercases, folds diacritics, strips leading/trailing punctuation, and
    collapses internal whitespace — so cosmetic noise a traveller might add
    ("friday!", "thứ 6.", double-spaced "hôm  nay") does not spuriously miss
    every branch and raise :class:`AmbiguousDateError`, forcing a needless
    follow-up question.

    :param raw: The traveller-supplied token, not yet lowercased/stripped.
    :return: The normalized token, ready for every branch below.
    """
    token = _EDGE_NOISE_RE.sub("", raw.strip().lower())
    token = fold_diacritics(token)
    return re.sub(r"\s+", " ", token).strip()


def _monday_of_week(day: date) -> date:
    """Return the Monday of the calendar week containing ``day``.

    :param day: Any date.
    :return: The Monday on/before ``day``.
    """
    return day - timedelta(days=day.weekday())


def _weekday_index(remainder: str) -> int | None:
    """Match a (folded, modifier-stripped) token against a weekday name.

    :param remainder: The token with any this/next modifier already removed.
    :return: A ``Monday=0..Sunday=6`` index, or None if not a weekday name.
    """
    if remainder in _WEEKDAY_NAMES:
        return _WEEKDAY_NAMES[remainder]
    if remainder == _SUNDAY_SHORTHAND:
        return 6
    match = _VN_NUMERIC_WEEKDAY_RE.match(remainder)
    if match:
        return int(match.group(1)) - 2
    return None


def _parse_weekday_phrase(token: str) -> tuple[int, str] | None:
    """Parse a normalized token as an optionally-modified weekday name.

    Strips a trailing VN modifier (" tuan sau" / " tuan nay") or a leading EN
    modifier ("next " / "this "), then matches what's left against a weekday
    name.

    :param token: The normalized (see :func:`_normalize`) token.
    :return: ``(weekday, modifier)`` if ``token`` names a weekday, where
        ``modifier`` is one of ``"bare"``, ``"this"``, ``"next"``; else None.
    """
    remainder, modifier = token, "bare"
    if remainder.endswith(_NEXT_WEEK_SUFFIX):
        remainder, modifier = remainder[: -len(_NEXT_WEEK_SUFFIX)], "next"
    elif remainder.endswith(_THIS_WEEK_SUFFIX):
        remainder, modifier = remainder[: -len(_THIS_WEEK_SUFFIX)], "this"
    if remainder.startswith(_NEXT_PREFIX):
        remainder, modifier = remainder[len(_NEXT_PREFIX) :], "next"
    elif remainder.startswith(_THIS_PREFIX):
        remainder, modifier = remainder[len(_THIS_PREFIX) :], "this"
    weekday = _weekday_index(remainder)
    if weekday is None:
        return None
    return weekday, modifier


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


def resolve_travel_date(raw: str, today: date) -> str:
    """Normalize a relative/weekday/partial date expression to ISO ``YYYY-MM-DD``.

    Handles, case-insensitively: ISO dates (validated, returned unchanged —
    the ISO and ``DD/MM(/YYYY)`` branches deliberately do not reject a past
    date; see the module docstring), relative day-words (today/tomorrow, hôm
    nay/ngày mai/ngày kia, bare mai/mốt), day-first ``DD/MM`` or
    ``DD/MM/YYYY`` (a missing year picks the nearest future occurrence),
    weekday names in English and Vietnamese (with and without diacritics,
    including "thứ 2".."thứ 7"/"t2".."t7"/"cn"), optionally modified by
    this/next ("next friday", "thứ 6 tuần sau", "thứ 6 tuần này" — see the
    module docstring for the pinned calendar-week semantics), "next
    week"/"tuần sau" (-> Monday of next week), "this weekend"/"cuối tuần
    này" and "next weekend"/"cuối tuần sau", and day offsets ("in 3 days", "3
    ngày nữa", bounded to 0..730 days).

    Surrounding punctuation and doubled whitespace ("friday!", "thứ 6.",
    "hôm  nay") are normalized away before matching, so cosmetic noise never
    forces an avoidable :class:`AmbiguousDateError`.

    :param raw: The traveller-supplied date token, possibly relative or partial.
    :param today: The current date in the traveller's timezone (grounds relatives).
    :returns: An ISO ``YYYY-MM-DD`` date string.
    :raises AmbiguousDateError: If ``raw`` cannot be resolved without guessing
        (an unrecognized phrase, a bare month/year with no day, a "this
        <weekday>" that already passed this week, or a day offset outside
        the 0..730 day window). Subclasses ``ValueError``.
    :raises ValueError: If ``raw`` is empty or names an invalid calendar date.
    """
    if not raw or not raw.strip():
        raise ValueError("empty date")
    try:
        return _resolve_normalized(raw, today)
    except (OverflowError, OSError) as e:
        # Belt-and-braces: an extreme numeric input (a huge year or day
        # offset) can overflow C-level date/timedelta arithmetic and raise
        # OverflowError/OSError instead of ValueError, which would escape
        # every ``except ValueError`` in the tool layer. Anything that
        # reaches here is unresolvable without guessing anyway.
        raise AmbiguousDateError(f"{raw!r} is out of range: {e}") from e


def _resolve_normalized(raw: str, today: date) -> str:
    """Do the actual parsing/matching for :func:`resolve_travel_date`.

    Split out so the top-level function can wrap it in one
    ``OverflowError``/``OSError`` safety net (see its docstring) without
    nesting that try/except around every branch below.

    :param raw: The traveller-supplied date token (non-empty).
    :param today: The current date in the traveller's timezone.
    :returns: An ISO ``YYYY-MM-DD`` date string.
    :raises AmbiguousDateError: See :func:`resolve_travel_date`.
    :raises ValueError: See :func:`resolve_travel_date`.
    """
    token = raw.strip().lower()

    # 1. Already ISO — validate and pass through untouched.
    try:
        return datetime.strptime(token, "%Y-%m-%d").date().isoformat()
    except ValueError:
        pass

    # 2. Slash/dash numeric forms.
    parts = token.replace("-", "/").split("/")
    if len(parts) in (2, 3) and all(p.isdigit() and p != "" for p in parts):
        # 2a. YYYY/MM/DD — a common model slip on the ISO format (dashes expected).
        # A 4-digit leading part is unambiguously a year, so read it ISO-order.
        if len(parts) == 3 and len(parts[0]) == 4:
            return date(int(parts[0]), int(parts[1]), int(parts[2])).isoformat()
        # 2b. A 2-part token whose second half is a 4-digit year (e.g.
        # "07/2026") is a bare month/year with no day — equally readable as
        # DD/MM (day 7, "month" 2026: invalid) or MM/YYYY with no day given.
        # Never guess which day of the month; raise instead.
        if len(parts) == 2 and len(parts[1]) == 4:
            raise AmbiguousDateError(f"{raw!r} has no day component (bare month/year)")
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
            raise ValueError(f"invalid date {raw!r}") from e
        if candidate < today:
            candidate = date(today.year + 1, month, day)
        return candidate.isoformat()

    # Everything below is matched against the normalized (folded,
    # punctuation/whitespace-cleaned) token — including the relative
    # day-words, which is why step 1 (ISO) and step 2 (slash/dash numeric)
    # run first: normalization must never perturb a literal numeric date.
    normalized = _normalize(raw)

    # 3. Relative day-words.
    if normalized in _RELATIVE_DAYS:
        return (today + timedelta(days=_RELATIVE_DAYS[normalized])).isoformat()

    # 4. Weekday names/shorthands, optionally this/next-modified.
    parsed = _parse_weekday_phrase(normalized)
    if parsed is not None:
        weekday, modifier = parsed
        if modifier == "next":
            next_monday = _monday_of_week(today) + timedelta(days=7)
            return (next_monday + timedelta(days=weekday)).isoformat()
        if modifier == "this":
            candidate = _monday_of_week(today) + timedelta(days=weekday)
            if candidate < today:
                raise AmbiguousDateError(f"{raw!r} already passed this calendar week")
            return candidate.isoformat()
        return _next_occurrence_strictly_after(today, weekday).isoformat()

    # 5. "next week" / "tuần sau" (bare) -> Monday of next calendar week.
    if normalized in ("next week", "tuan sau"):
        return (_monday_of_week(today) + timedelta(days=7)).isoformat()

    # 6. "this weekend" / "cuối tuần này" -> the Saturday of the current
    # calendar week — or today, if the weekend is already underway.
    if normalized in ("this weekend", "cuoi tuan nay"):
        if today.weekday() in (5, 6):  # Sat or Sun: this weekend is now.
            return today.isoformat()
        return (_monday_of_week(today) + timedelta(days=5)).isoformat()

    # 7. "next weekend" / "cuối tuần sau" -> the Saturday of next calendar week.
    if normalized in ("next weekend", "cuoi tuan sau"):
        return (_monday_of_week(today) + timedelta(days=12)).isoformat()

    # 8. Day offsets: "in N day(s)" / "N ngày nữa", bounded to a sane
    # travel-planning window (see ``_MAX_DAY_OFFSET``).
    offset_match = _DAY_OFFSET_EN_RE.match(normalized) or _DAY_OFFSET_VN_RE.match(
        normalized
    )
    if offset_match:
        offset = int(offset_match.group(1))
        if offset > _MAX_DAY_OFFSET:
            raise AmbiguousDateError(
                f"{raw!r} is too far out ({offset} days; max {_MAX_DAY_OFFSET})"
            )
        return (today + timedelta(days=offset)).isoformat()

    raise AmbiguousDateError(f"unrecognized date {raw!r}")


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
