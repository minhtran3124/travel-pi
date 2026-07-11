"""Structured date-parsing intent returned by the ``date_resolution`` LLM.

The model (any language, any phrasing) never returns a computed date — it
returns a :class:`DateIntent`, and :func:`app.core.dates.compute_from_intent`
does the arithmetic in code. This split exists because language understanding
is what an LLM is good at and date arithmetic is what it is bad at (a wrong
"+7" is invisible in prose but breaks a search); see
``specs/agent-date-resolution/PLAN.md`` section 4b.

Every field description below is fed straight into the model's
function-calling schema — it is prompt surface, not just documentation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.base import AppBaseModel


class DateIntent(AppBaseModel):
    """The traveller's date expression, parsed but not yet computed."""

    kind: Literal[
        "absolute",
        "relative_day",
        "weekday",
        "week_start",
        "weekend",
        "offset",
        "ambiguous",
    ] = Field(
        description=(
            "The shape of the date expression. 'absolute': an explicit "
            "calendar date (day/month[/year]). 'relative_day': today, "
            "tomorrow, or the day after tomorrow. 'weekday': a named day of "
            "the week (e.g. 'Friday', 'thứ 6'), optionally qualified by "
            "'this'/'next'. 'week_start': the start (Monday) of the current "
            "or next calendar week, with no specific weekday named. "
            "'weekend': the weekend of the current or next calendar week. "
            "'offset': an explicit count of days from today (e.g. 'in 3 "
            "days'). 'ambiguous': the expression cannot be mapped to a date "
            "without inventing information the traveller did not give — "
            "always prefer this over guessing."
        )
    )
    year: int | None = Field(
        default=None,
        description=(
            "Calendar year, only for kind='absolute'. Omit (null) when the "
            "traveller gave no year — the caller picks the nearest future "
            "occurrence of that day/month."
        ),
    )
    month: int | None = Field(
        default=None,
        description="Calendar month (1-12), only for kind='absolute'.",
    )
    day: int | None = Field(
        default=None,
        description="Day of month (1-31), only for kind='absolute'.",
    )
    day_offset: int | None = Field(
        default=None,
        description=(
            "Number of days from today. For kind='relative_day': today=0, "
            "tomorrow=1, day-after-tomorrow=2. For kind='offset': the "
            "explicit number of days the traveller named (e.g. 'in 3 days' "
            "-> 3). Not used for any other kind."
        ),
    )
    weekday: int | None = Field(
        default=None,
        description=(
            "Target day of the week, only for kind='weekday'. "
            "0=Monday, 1=Tuesday, 2=Wednesday, 3=Thursday, 4=Friday, "
            "5=Saturday, 6=Sunday."
        ),
    )
    week: Literal["current", "next", "bare"] | None = Field(
        default=None,
        description=(
            "Which calendar week the expression refers to, for "
            "kind='weekday', 'week_start', or 'weekend'. 'bare': no "
            "'this'/'next' qualifier was given (only valid for 'weekday' — "
            "it means the next occurrence of that weekday strictly after "
            "today). 'current': explicitly 'this <weekday>'/'this "
            "week'/'this weekend' — the calendar week today falls in. "
            "'next': explicitly 'next <weekday>'/'next week'/'next "
            "weekend' — the following calendar week."
        ),
    )
    reason: str | None = Field(
        default=None,
        description=(
            "Only for kind='ambiguous'. A short explanation, in the "
            "traveller's own language, of what is missing or unclear — this "
            "is shown back to the traveller as the follow-up question."
        ),
    )
