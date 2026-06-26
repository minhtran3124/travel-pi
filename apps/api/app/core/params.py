"""Shared coercion helpers for query-param strings.

HTML forms submit empty fields as ``""`` and the JSON API accepts free-text
numeric strings; both sites used to do their own ``float()`` / ``int()``
gymnastics with subtly different range checks (and one path 500'd on bad
input). One helper here is the single source of truth — callers decide
what to do with the error string (raise an HTTP 422 in the JSON API,
render an inline message on a dashboard page).
"""

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
    """Parse an optional numeric query-param into ``(value, error)``.

    Returns ``(None, None)`` for ``None`` or an empty/whitespace string —
    the same "treat blank as not filtered" semantics every form needs.

    On a non-numeric or out-of-range input returns ``(None, message)`` with
    a friendly, label-prefixed error the caller can render or wrap in a
    422. The value is never returned alongside an error.

    ``kind`` is ``int`` or ``float``. Bounds are inclusive when supplied.
    """
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
