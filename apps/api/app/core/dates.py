"""Deterministic resolution of the relative/weekday/partial travel-date forms.

A safety net beneath the LLM: rather than trusting the model to do date
arithmetic in its head ("next Friday", "cuối tuần này"), the agent sends the
traveller's literal expression through :func:`resolve_travel_date` and passes
the resulting ISO date to a tool. This module owns every form travellers
commonly type, so the LLM never has to compute a date itself.

Weekday/phrase semantics (pinned, not just "a sensible convention" — see
:class:`AmbiguousDateError` for the alternative):

- A **bare** weekday ("friday", "thứ 6") or a **"this"-prefixed** weekday
  ("this friday", "thứ 6 tuần này") resolves to the next occurrence of that
  weekday **strictly after** ``today`` — never today itself, never the past.
- A **"next"-prefixed** weekday ("next friday", "thứ 6 tuần sau") resolves to
  that same occurrence **plus 7 days**.
- Nothing here ever resolves into the past, and nothing that would require
  guessing resolves at all — nothing this module can't parse, or a bare
  month/year with no day, raises :class:`AmbiguousDateError` instead.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


class AmbiguousDateError(ValueError):
    """Raised when a date expression cannot be resolved without guessing.

    Subclasses :class:`ValueError` so existing ``except ValueError`` callers
    (``flight_tools``, ``hotel_tools``) keep working unchanged; callers that
    want to route ambiguity to a traveller-facing question can catch this
    type specifically.
    """


# Relative day-words (English + Vietnamese, with/without diacritics) -> offset.
_RELATIVE_DAYS: dict[str, int] = {
    "today": 0,
    "hôm nay": 0,
    "hom nay": 0,
    "tomorrow": 1,
    "ngày mai": 1,
    "ngay mai": 1,
    "mai": 1,
    "day after tomorrow": 2,
    "ngày kia": 2,
    "ngay kia": 2,
    "mốt": 2,
    "mot": 2,
}

# Weekday names (English + Vietnamese, diacritics already folded — see
# ``_fold_diacritics``) -> Python's Monday=0..Sunday=6.
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


def _fold_diacritics(text: str) -> str:
    """Fold Vietnamese diacritics to their base ASCII letters.

    Mirrors the normalisation in :mod:`app.core.text` so weekday/phrase
    matching accepts accented and unaccented Vietnamese input against a
    single dictionary entry, instead of doubling every key. ``đ`` (U+0111)
    has no canonical NFD decomposition, so it is mapped explicitly; the rest
    decompose to a base letter plus a combining mark, which is then dropped.

    :param text: Already-lowercased text to fold.
    :return: The diacritic-folded text.
    """
    folded = text.replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", folded)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


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


def _parse_weekday_phrase(folded: str) -> tuple[int, bool] | None:
    """Parse a folded token as an optionally-modified weekday name.

    Strips a trailing VN modifier (" tuần sau" / " tuần này") or a leading EN
    modifier ("next " / "this "), then matches what's left against a weekday
    name. Only the "next" forms set ``is_next`` — a bare or "this" token is
    always the strictly-future occurrence.

    :param folded: The lowercased, diacritic-folded, whitespace-collapsed token.
    :return: ``(weekday, is_next)`` if ``folded`` names a weekday, else None.
    """
    remainder, is_next = folded, False
    if remainder.endswith(_NEXT_WEEK_SUFFIX):
        remainder, is_next = remainder[: -len(_NEXT_WEEK_SUFFIX)], True
    elif remainder.endswith(_THIS_WEEK_SUFFIX):
        remainder = remainder[: -len(_THIS_WEEK_SUFFIX)]
    if remainder.startswith(_NEXT_PREFIX):
        remainder, is_next = remainder[len(_NEXT_PREFIX) :], True
    elif remainder.startswith(_THIS_PREFIX):
        remainder = remainder[len(_THIS_PREFIX) :]
    weekday = _weekday_index(remainder)
    if weekday is None:
        return None
    return weekday, is_next


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

    Handles, case-insensitively: ISO dates (validated, returned unchanged),
    relative day-words (today/tomorrow, hôm nay/ngày mai/ngày kia, bare
    mai/mốt), day-first ``DD/MM`` or ``DD/MM/YYYY`` (a missing year picks the
    nearest future occurrence), weekday names in English and Vietnamese (with
    and without diacritics, including "thứ 2".."thứ 7"/"t2".."t7"/"cn"),
    optionally modified by this/next ("next friday", "thứ 6 tuần sau", "thứ 6
    tuần này" — see the module docstring for the pinned strictly-future
    semantics), "next week"/"tuần sau" (-> Monday of next week), "this
    weekend"/"cuối tuần này" (-> the coming Saturday), and day offsets ("in 3
    days", "3 ngày nữa").

    :param raw: The traveller-supplied date token, possibly relative or partial.
    :param today: The current date in the traveller's timezone (grounds relatives).
    :returns: An ISO ``YYYY-MM-DD`` date string.
    :raises AmbiguousDateError: If ``raw`` cannot be resolved without guessing
        (an unrecognized phrase, or a bare month/year with no day). Subclasses
        ``ValueError``.
    :raises ValueError: If ``raw`` is empty or names an invalid calendar date.
    """
    if not raw or not raw.strip():
        raise ValueError("empty date")
    token = raw.strip().lower()

    # 1. Already ISO — validate and pass through untouched.
    try:
        return datetime.strptime(token, "%Y-%m-%d").date().isoformat()
    except ValueError:
        pass

    # 2. Relative day-words.
    if token in _RELATIVE_DAYS:
        return (today + timedelta(days=_RELATIVE_DAYS[token])).isoformat()

    # 3. Slash/dash numeric forms.
    parts = token.replace("-", "/").split("/")
    if len(parts) in (2, 3) and all(p.isdigit() and p != "" for p in parts):
        # 3a. YYYY/MM/DD — a common model slip on the ISO format (dashes expected).
        # A 4-digit leading part is unambiguously a year, so read it ISO-order.
        if len(parts) == 3 and len(parts[0]) == 4:
            return date(int(parts[0]), int(parts[1]), int(parts[2])).isoformat()
        # 3b. A 2-part token whose second half is a 4-digit year (e.g.
        # "07/2026") is a bare month/year with no day — equally readable as
        # DD/MM (day 7, "month" 2026: invalid) or MM/YYYY with no day given.
        # Never guess which day of the month; raise instead.
        if len(parts) == 2 and len(parts[1]) == 4:
            raise AmbiguousDateError(f"{raw!r} has no day component (bare month/year)")
        # 3c. Day-first DD/MM/YYYY or DD/MM (year inferred).
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

    folded = re.sub(r"\s+", " ", _fold_diacritics(token)).strip()

    # 4. Weekday names/shorthands, optionally this/next-modified.
    parsed = _parse_weekday_phrase(folded)
    if parsed is not None:
        weekday, is_next = parsed
        result = _next_occurrence_strictly_after(today, weekday)
        if is_next:
            result += timedelta(days=7)
        return result.isoformat()

    # 5. "next week" / "tuần sau" (bare) -> Monday of next calendar week.
    if folded in ("next week", "tuan sau"):
        current_monday = today - timedelta(days=today.weekday())
        return (current_monday + timedelta(days=7)).isoformat()

    # 6. "this weekend" / "cuối tuần này" -> the coming Saturday (strictly
    # future, same rule as a bare/this-prefixed weekday).
    if folded in ("this weekend", "cuoi tuan nay"):
        return _next_occurrence_strictly_after(today, 5).isoformat()

    # 7. Day offsets: "in N day(s)" / "N ngày nữa".
    offset_match = _DAY_OFFSET_EN_RE.match(folded) or _DAY_OFFSET_VN_RE.match(folded)
    if offset_match:
        return (today + timedelta(days=int(offset_match.group(1)))).isoformat()

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
