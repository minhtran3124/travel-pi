"""Shared coercion helper for optional numeric query-param strings — one source of truth for parsing and range checks; callers decide what to do with the error string."""

from typing import TypeVar

NumberT = TypeVar("NumberT", int, float)


def parse_optional_number(
    raw: str | None,
    *,
    label: str,
    kind: type[NumberT],
    minimum: float | None = None,
    maximum: float | None = None,
) -> tuple[NumberT | None, str | None]:
    """Parse an optional numeric query-param into ``(value, error)``: blank/None → ``(None, None)``, bad or out-of-range (inclusive bounds) → ``(None, message)``; never both."""
    if raw is None:
        return None, None
    text = raw.strip() if isinstance(raw, str) else raw
    if text == "" or text is None:
        return None, None
    try:
        value = kind(text)
    except (TypeError, ValueError):
        type_name = "an integer" if kind is int else "a number"
        return None, f"{label} must be {type_name}."
    if minimum is not None and value < minimum:
        return None, f"{label} must be at least {minimum}."
    if maximum is not None and value > maximum:
        return None, f"{label} must be at most {maximum}."
    return value, None
