"""Deterministic resolution of the common relative/partial travel-date forms.

A safety net beneath the LLM: the model is expected to resolve rich natural
language ("next Friday", "cuối tuần này") against the grounded current date and
pass ISO to a tool. This helper only backstops the simple forms travellers most
often type, so one slip in that resolution does not dead-end a flight/hotel
search. Weekday/phrase parsing is deliberately out of scope.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

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


def resolve_travel_date(raw: str, today: date) -> str:
    """Normalize a simple relative/partial date to an ISO ``YYYY-MM-DD`` string.

    Handles, case-insensitively: ISO dates (validated, returned unchanged),
    relative day-words (today/tomorrow, hôm nay/ngày mai/ngày kia, bare mai/mốt),
    and day-first ``DD/MM`` or ``DD/MM/YYYY`` (a missing year picks the nearest
    future occurrence). Weekday/phrase forms are NOT parsed here — the LLM
    resolves those against the grounded date.

    :param raw: The traveller-supplied date token, possibly relative or partial.
    :param today: The current date in the traveller's timezone (grounds relatives).
    :returns: An ISO ``YYYY-MM-DD`` date string.
    :raises ValueError: If ``raw`` is empty or not a recognized simple form.
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
        # 3b. Day-first DD/MM/YYYY or DD/MM (year inferred).
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

    raise ValueError(f"unrecognized date {raw!r}")


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
