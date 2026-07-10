---
slug: flight-search-date-context
status: shipped
owner: Minh Tran
created: 2026-07-09
---

# Flight & Hotel Date Awareness + Multi-Turn Stitching — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans (or subagent-driven-development) to implement this plan task-by-task.

**Goal:** Make flight & hotel info-collection resolve relative/partial dates against the correct local "today", stitch info the traveller gave across recent turns, and confirm the resolved date once — instead of looping on questions already answered.

**Architecture:** Hybrid, four layers. (A) A per-request IANA `timezone` flows FE → `ChatRequest` → `AgentContext` → `ground_current_date(base, tz)`. (B) The supervisor is grounded too and grounding uses the request tz instead of UTC. (C) A new deterministic `resolve_travel_date` helper normalizes simple relative/partial dates in the flight & hotel tools as a backstop. (D) New `planner`/`booking` prompt versions reframe the `never guess dates` rule (which currently blocks resolution/stitching) and reinforce confirm-then-call.

**Tech Stack:** FastAPI, LangGraph 1.0 (context channel), Pydantic v2, pydantic-settings, pytest, `zoneinfo` (stdlib).

**Lane:** normal. See `specs/flight-search-date-context/SUMMARY.md`, `design.md`, `research-brief.md`.

---

## Wave map

| Wave | Tasks | Parallel | Files (disjoint per wave) |
|------|-------|----------|---------------------------|
| 1 | 1.1 config, 1.2 dates helper, 1.3 context field, 1.4 schema field | 4 | `config.py` / `core/dates.py` / `agents/context.py` / `schemas/agent.py` |
| 2 | 2.1 grounding tz, 2.2 flight tool, 2.3 hotel tool | 3 | `agents/state.py` / `tools/flight_tools.py` / `tools/hotel_tools.py` |
| 3 | 3.1 sub-agent node, 3.2 supervisor, 3.3 router threading | 3 | `subagents/_base.py` / `agents/supervisor.py` / `routers/agent.py` |
| 4 | 4.1 prompts v6/v5 + active.yaml | 1 | `prompts/planner/v6.md`, `prompts/booking/v5.md`, `prompts/active.yaml` |
| 5 | 5.1 full-suite + rebuild verify, 5.2 FE sends tz (cross-stack) | — | `apps/web/…` |

**Dependencies:** 2.2/2.3 need 1.2 (`dates.py`). 3.1/3.2 need 2.1 (new `ground_current_date` signature) + 1.3 (`AgentContext.timezone`). 3.3 needs 1.1 + 1.3 + 1.4.

**Env caveat (all pytest runs):** `apps/api/.env` sets `OPENAI_API_KEY=test` and a Postgres `DATABASE_URL` that break LLM/lifespan/DB tests. Pure unit tasks (1.2, 1.3, 1.4, 2.1) are unaffected. Any test that hits the DB or lifespan — the tool tests (2.2, 2.3, they call `session_scope()`), the router test (3.3), and the full suite (5.1) — must prefix `DATABASE_URL=sqlite:///./travel.db` or use `make test` (zero-config SQLite). See memory `env-openai-key-test-breaks-llm-tests`.

---

## Chunk 1: All implementation tasks

### Task 1.1 — Add `agent_timezone` setting

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/core/config.py</files>
  <action>In the "Agent runtime knobs" block (after `agent_config_cache_ttl_seconds`, ~line 176), add `agent_timezone: str = "Asia/Ho_Chi_Minh"  # default IANA tz for grounding relative dates when the client sends none`. Pydantic-settings reads it from env var `AGENT_TIMEZONE` (UPPERCASE field name). No other change.</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "from app.core.config import get_settings; print(get_settings().agent_timezone)"</verify>
  <done>Prints `Asia/Ho_Chi_Minh`; importable, no error.</done>
</task>
```

Add exactly:

```python
    agent_config_cache_ttl_seconds: int = 3600
    # Default IANA timezone used to ground "today" for relative-date resolution
    # when the client does not send a valid timezone (see specs/flight-search-date-context).
    agent_timezone: str = "Asia/Ho_Chi_Minh"
```

---

### Task 1.2 — New deterministic date helper `resolve_travel_date`

```xml
<task id="1.2" wave="1">
  <files>apps/api/app/core/dates.py, apps/api/tests/core/test_dates.py</files>
  <action>Create `app/core/dates.py` with `resolve_travel_date(raw, today) -> str` — a deterministic backstop that normalizes ISO, relative day words (EN + VN), and day-first `DD/MM[/YYYY]` to ISO. Missing year picks the nearest FUTURE occurrence. Weekday/phrase forms ("next Friday") are intentionally NOT parsed (the LLM resolves those); unrecognized input raises `ValueError`.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_dates.py -x</verify>
  <done>All helper unit tests pass.</done>
</task>
```

- [ ] **Step 1: Write the failing test** — `apps/api/tests/core/test_dates.py`

```python
from datetime import date

import pytest

from app.core.dates import resolve_travel_date

TODAY = date(2026, 7, 9)  # a Thursday


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-07-10", "2026-07-10"),      # ISO passthrough
        ("today", "2026-07-09"),
        ("hôm nay", "2026-07-09"),
        ("tomorrow", "2026-07-10"),
        ("ngày mai", "2026-07-10"),
        ("Ngày Mai", "2026-07-10"),        # case-insensitive
        ("mai", "2026-07-10"),
        ("ngày kia", "2026-07-11"),
        ("10/07/2026", "2026-07-10"),      # DD/MM/YYYY (day-first)
        ("10-07-2026", "2026-07-10"),      # dash day-first
        ("10/07", "2026-07-10"),           # DD/MM, year inferred (this year)
        ("08/07", "2027-07-08"),           # DD/MM already past -> next year
    ],
)
def test_resolves_simple_forms(raw, expected):
    assert resolve_travel_date(raw, TODAY) == expected


@pytest.mark.parametrize("raw", ["", "   ", "next friday", "someday", "07/2026", "99/99"])
def test_rejects_unresolvable(raw):
    with pytest.raises(ValueError):
        resolve_travel_date(raw, TODAY)
```

- [ ] **Step 2: Run it — expect FAIL** (`ModuleNotFoundError: app.core.dates`)

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_dates.py -x`

- [ ] **Step 3: Implement** — `apps/api/app/core/dates.py`

```python
"""Deterministic resolution of the common relative/partial travel-date forms.

A safety net beneath the LLM: the model is expected to resolve rich natural
language ("next Friday", "cuối tuần này") against the grounded current date and
pass ISO to a tool. This helper only backstops the simple forms travellers most
often type, so one slip in that resolution does not dead-end a flight/hotel
search. Weekday/phrase parsing is deliberately out of scope.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

# Relative day-words (English + Vietnamese, with/without diacritics) -> offset.
_RELATIVE_DAYS: dict[str, int] = {
    "today": 0, "hôm nay": 0, "hom nay": 0,
    "tomorrow": 1, "ngày mai": 1, "ngay mai": 1, "mai": 1,
    "day after tomorrow": 2, "ngày kia": 2, "ngay kia": 2, "mốt": 2, "mot": 2,
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

    # 3. Day-first slash/dash forms: DD/MM/YYYY or DD/MM (year inferred).
    parts = token.replace("-", "/").split("/")
    if len(parts) in (2, 3) and all(p.isdigit() and p != "" for p in parts):
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
```

- [ ] **Step 4: Run it — expect PASS**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_dates.py -x`

> Note: `app/core/dates.py` is a fresh module; the `ruff-on-edit` hook won't strip imports it uses. Keep `date`, `datetime`, `timedelta` all referenced (they are).

---

### Task 1.3 — Add `timezone` to `AgentContext` + `resolve_agent_context`

```xml
<task id="1.3" wave="1">
  <files>apps/api/app/agents/context.py, apps/api/tests/agents/test_context.py</files>
  <action>Add a `timezone: str | None = None` field to the frozen `AgentContext` dataclass (last field, default None preserves behavior), and a matching `timezone: str | None = None` keyword param to `resolve_agent_context`, passed straight through into the returned `AgentContext(...)`. Follows the existing `allow_reflection` pass-through exactly.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_context.py -x</verify>
  <done>Context carries timezone; default None; existing context tests still pass.</done>
</task>
```

- [ ] **Step 1: Write the failing test** — append to `apps/api/tests/agents/test_context.py` (create if absent)

```python
from app.agents.context import AgentContext, resolve_agent_context


def test_context_timezone_defaults_none():
    assert AgentContext().timezone is None


def test_resolve_agent_context_threads_timezone():
    ctx = resolve_agent_context(tier="free", timezone="Asia/Ho_Chi_Minh")
    assert ctx.timezone == "Asia/Ho_Chi_Minh"


def test_resolve_agent_context_timezone_optional():
    assert resolve_agent_context(tier="free").timezone is None
```

- [ ] **Step 2: Run it — expect FAIL** (`TypeError: unexpected keyword 'timezone'`)

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_context.py -x`

- [ ] **Step 3: Implement** — edit `app/agents/context.py`

Add as the last field of `AgentContext` (after `max_revisions`):

```python
    max_revisions: int = 1
    # Per-request IANA timezone used to ground "today" for relative-date
    # resolution; None keeps the legacy UTC behavior.
    timezone: str | None = None
```

Change the `resolve_agent_context` signature and its return:

```python
def resolve_agent_context(
    *, tier: Tier | str | None, allow_reflection: bool = True, timezone: str | None = None
) -> AgentContext:
```

```python
    return AgentContext(
        tier=tier,
        allow_reflection=allow_reflection,
        allow_memory_write=True,
        allow_episodic=True,
        response_style=ResponseStyle.DEFAULT,
        allowed_subagents=allowed_subagents,
        max_revisions=1,
        timezone=timezone,
    )
```

- [ ] **Step 4: Run it — expect PASS**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_context.py -x`

---

### Task 1.4 — Add optional `timezone` to `ChatRequest`

```xml
<task id="1.4" wave="1">
  <files>apps/api/app/schemas/agent.py, apps/api/tests/api/agent/test_agent_schemas.py</files>
  <action>Add an optional additive field `timezone: str | None = Field(default=None, ...)` to `ChatRequest` (after `resume`). Backward-compatible: omitting it stays valid. Do NOT add validation here — the router validates via zoneinfo and falls back, so a bad value must not 422 the request.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_agent_schemas.py -x</verify>
  <done>ChatRequest accepts with/without timezone; a garbage tz string still parses (router will fall back).</done>
</task>
```

- [ ] **Step 1: Write the failing test** — `apps/api/tests/api/agent/test_agent_schemas.py` (create if absent)

```python
from app.schemas.agent import ChatRequest


def test_chat_request_accepts_timezone():
    req = ChatRequest(message="hi", user_id="u1", timezone="Asia/Ho_Chi_Minh")
    assert req.timezone == "Asia/Ho_Chi_Minh"


def test_chat_request_timezone_optional():
    assert ChatRequest(message="hi", user_id="u1").timezone is None


def test_chat_request_bad_timezone_still_parses():
    # Router validates + falls back; schema must not 422 on a bad tz string.
    assert ChatRequest(message="hi", user_id="u1", timezone="Not/AZone").timezone == "Not/AZone"
```

- [ ] **Step 2: Run it — expect FAIL** (`timezone` unknown / attribute error)

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_agent_schemas.py -x`

- [ ] **Step 3: Implement** — edit `app/schemas/agent.py`, add after the `resume` field (before the `@model_validator`):

```python
    timezone: str | None = Field(
        default=None,
        description="Traveller's IANA timezone (e.g. 'Asia/Ho_Chi_Minh') detected by the "
        "client via Intl.DateTimeFormat().resolvedOptions().timeZone. Used to ground "
        "relative dates like 'tomorrow'. Invalid or missing falls back to the server default.",
    )
```

- [ ] **Step 4: Run it — expect PASS**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_agent_schemas.py -x`

---

### Task 2.1 — Timezone-aware `ground_current_date`

```xml
<task id="2.1" wave="2">
  <files>apps/api/app/agents/state.py, apps/api/tests/agents/test_state.py</files>
  <action>Add an optional `tz: str | None = None` param to `ground_current_date`. When `tz` is a valid IANA name, compute "today" in that zone and label the note with the zone; otherwise keep the exact current UTC behavior. Guard invalid tz -> UTC fallback (defense-in-depth; router already validates). Add `from zoneinfo import ZoneInfo` import.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_state.py -x</verify>
  <done>tz-less call byte-for-byte preserves old note; tz call grounds the local date + labels the zone; existing state tests pass.</done>
</task>
```

- [ ] **Step 1: Write the failing test** — append to `apps/api/tests/agents/test_state.py`

```python
def test_ground_current_date_uses_timezone():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from langchain_core.messages import SystemMessage

    from app.agents.state import ground_current_date

    tz = "Asia/Ho_Chi_Minh"
    today_local = datetime.now(ZoneInfo(tz)).strftime("%Y-%m-%d")
    grounded = ground_current_date(SystemMessage(content="BASE"), tz)
    assert today_local in grounded.content
    assert tz in grounded.content
    assert "BASE" in grounded.content


def test_ground_current_date_invalid_tz_falls_back_to_utc():
    from langchain_core.messages import SystemMessage

    from app.agents.state import ground_current_date

    grounded = ground_current_date(SystemMessage(content="BASE"), "Not/AZone")
    assert "UTC" in grounded.content  # fell back, did not raise
```

(Existing `test_ground_current_date_injects_today` must still pass unchanged — it calls with one arg.)

- [ ] **Step 2: Run it — expect FAIL** (`ground_current_date() takes 1 positional arg`)

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_state.py -x`

- [ ] **Step 3: Implement** — edit `app/agents/state.py`. Add near the top imports: `from zoneinfo import ZoneInfo`. Replace the body of `ground_current_date`:

```python
def ground_current_date(base: SystemMessage, tz: str | None = None) -> SystemMessage:
    """Prepend today's date so the model resolves relative dates instead of guessing.

    Without a concrete "today", the model has to invent a date when the traveller
    says something like "hôm nay"/"today" or "next Friday", which then flows into
    tool calls such as ``search_flights(departure_date=...)``. Grounding a real date
    lets it resolve those expressions and forbids fabricating a date that was never
    given. Computed per request — the graph is built once at startup, so a long-
    running server would otherwise serve a date frozen at boot.

    :param base: The base system message to fold the date grounding into.
    :param tz: Optional IANA timezone (e.g. "Asia/Ho_Chi_Minh") for the traveller;
        grounds "today" in their local zone. Invalid/None falls back to UTC.
    :return: A ``SystemMessage`` with ``base`` followed by the date-grounding note.
    """
    zone_label = "UTC"
    now = datetime.now(timezone.utc)
    if tz:
        try:
            now = datetime.now(ZoneInfo(tz))
            zone_label = tz
        except Exception:  # unknown/invalid tz -> keep UTC
            now = datetime.now(timezone.utc)
            zone_label = "UTC"
    today = now.strftime("%Y-%m-%d")
    note = (
        f"CURRENT DATE: today is {today} ({zone_label}). This is the only correct "
        'value for "today". Resolve every relative date ("today", "tomorrow", '
        '"next Friday", "this weekend") against it, and never pass a tool a date '
        f"earlier than {today}. If the traveller has not given enough to derive a "
        "concrete date, ask them — do not guess or invent one."
    )
    return SystemMessage(content=f"{note}\n\n{base.content}")
```

- [ ] **Step 4: Run it — expect PASS** (new + old state tests)

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_state.py -x`

---

### Task 2.2 — Flight tool resolves relative/partial dates

```xml
<task id="2.2" wave="2">
  <files>apps/api/app/tools/flight_tools.py, apps/api/tests/api/tools/test_flight_tools_dates.py</files>
  <action>Before the strict `strptime`, normalize `departure_date` via `resolve_travel_date`, and compute `today` from the configured `agent_timezone` (not UTC) so the deterministic backstop matches the grounded audience. Wrap resolution in the existing try/except so unresolved input raises the same guidance ToolException. Import `resolve_travel_date`, `get_settings`, `ZoneInfo`; the old `datetime.now(timezone.utc)` was the only `timezone` use, so change `from datetime import datetime, timezone` → `from datetime import datetime` (else F401).</action>
  <verify>cd apps/api && DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest tests/api/tools/test_flight_tools_dates.py -x</verify>
  <done>"ngày mai"/"10/07" resolve and search; unparseable raises ToolException; past ISO still rejected.</done>
</task>
```

> **Scoping note (deliberate):** tools read `InjectedState`, not the `AgentContext` context channel, so the per-request tz isn't cleanly available inside a tool. The tool's `today` therefore uses the *configured default* `agent_timezone` — a correct deterministic backstop for the primary audience. Per-request tz still governs the prompt grounding (Task 2.1/3.x), which is the primary lever. Do NOT try to thread per-request tz into tools in this plan.

- [ ] **Step 1: Write the failing test** — `apps/api/tests/api/tools/test_flight_tools_dates.py`

```python
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from langchain_core.tools import ToolException

from app.core.config import get_settings
from app.tools.flight_tools import search_flights


def _today_iso():
    return datetime.now(ZoneInfo(get_settings().agent_timezone)).date().isoformat()


def test_relative_date_resolves_and_searches():
    # "ngày mai" must not raise a bad-format ToolException; it resolves + returns a summary.
    summary, _artifact = search_flights.invoke(
        {"origin": "DAD", "destination": "SGN", "departure_date": "ngày mai"}
    )
    assert isinstance(summary, str) and summary


def test_unparseable_date_raises_toolexception():
    with pytest.raises(ToolException):
        search_flights.invoke(
            {"origin": "DAD", "destination": "SGN", "departure_date": "someday"}
        )
```

- [ ] **Step 2: Run it — expect FAIL** ("ngày mai" hits the strict strptime → ToolException)

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/api/tools/test_flight_tools_dates.py -x`

- [ ] **Step 3: Implement** — edit `app/tools/flight_tools.py`. Add imports near the top, and trim the now-unused `timezone` from the datetime import (`from datetime import datetime, timezone` → `from datetime import datetime`):

```python
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.core.dates import resolve_travel_date
```

Replace the `today`/`try` parse block (currently lines ~85-93) with:

```python
    log_tool_call("search_flights", locals())
    today = datetime.now(ZoneInfo(get_settings().agent_timezone)).date()
    try:
        departure_date = resolve_travel_date(departure_date, today)
        parsed_date = datetime.strptime(departure_date, "%Y-%m-%d").date()
    except ValueError as e:
        raise ToolException(
            f"departure_date {departure_date!r} could not be resolved to a concrete "
            f"YYYY-MM-DD date. Today is {today.isoformat()}. Resolve relative terms "
            "(e.g. 'tomorrow') against today and ask the traveller for a concrete date."
        ) from e
```

(The `if parsed_date < today:` past-date block below stays unchanged; `departure_date` is now normalized ISO so its downstream use is correct.)

- [ ] **Step 4: Run it — expect PASS**

Run: `cd apps/api && DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest tests/api/tools/test_flight_tools_dates.py -x`

---

### Task 2.3 — Hotel `search_hotels` resolves relative/partial dates

```xml
<task id="2.3" wave="2">
  <files>apps/api/app/tools/hotel_tools.py, apps/api/tests/api/tools/test_hotel_tools_dates.py</files>
  <action>Mirror 2.2 in `search_hotels`: normalize BOTH `check_in` and `check_out` via `resolve_travel_date` against a `agent_timezone`-based `today`, inside the existing try/except. Do NOT touch `book_hotel` (dates arrive already-ISO from a prior search) or `browse_hotels` (date-less). Import `resolve_travel_date`, `get_settings`, `ZoneInfo`; if `datetime.now(timezone.utc)` was the only `timezone` use, trim `from datetime import datetime, timezone` → `from datetime import datetime` (else F401 — verify the file has no other `timezone` reference first).</action>
  <verify>cd apps/api && DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest tests/api/tools/test_hotel_tools_dates.py -x</verify>
  <done>Relative/partial check-in & check-out resolve; unparseable raises ToolException; past check_in still rejected.</done>
</task>
```

- [ ] **Step 1: Write the failing test** — `apps/api/tests/api/tools/test_hotel_tools_dates.py`

```python
import pytest
from langchain_core.tools import ToolException

from app.tools.hotel_tools import search_hotels


def test_relative_hotel_dates_resolve():
    summary, _artifact = search_hotels.invoke(
        {
            "city": "Da Nang",
            "check_in": "ngày mai",
            "check_out": "ngày kia",
            "rooms": 1,
            "adults": 2,
            "children": 0,
        }
    )
    assert isinstance(summary, str) and summary


def test_unparseable_check_in_raises():
    with pytest.raises(ToolException):
        search_hotels.invoke(
            {
                "city": "Da Nang",
                "check_in": "someday",
                "check_out": "ngày kia",
                "rooms": 1,
                "adults": 2,
                "children": 0,
            }
        )
```

- [ ] **Step 2: Run it — expect FAIL** ("ngày mai" hits strict strptime)

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/api/tools/test_hotel_tools_dates.py -x`

- [ ] **Step 3: Implement** — edit `app/tools/hotel_tools.py`. Add the same three imports (if not already present). Replace the `today`/`try` block (currently ~166-174) with:

```python
    log_tool_call("search_hotels", locals())
    today = datetime.now(ZoneInfo(get_settings().agent_timezone)).date()
    try:
        check_in = resolve_travel_date(check_in, today)
        check_out = resolve_travel_date(check_out, today)
        parsed_check_in = datetime.strptime(check_in, "%Y-%m-%d").date()
    except ValueError as e:
        raise ToolException(
            f"check_in {check_in!r} / check_out {check_out!r} could not be resolved to "
            f"concrete YYYY-MM-DD dates. Today is {today.isoformat()}. Resolve relative "
            "terms against today and ask the traveller for concrete dates."
        ) from e
```

(The `if parsed_check_in < today:` block below stays unchanged; both dates are now normalized ISO.)

- [ ] **Step 4: Run it — expect PASS**

Run: `cd apps/api && DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest tests/api/tools/test_hotel_tools_dates.py -x`

---

### Task 3.1 — Sub-agent node passes tz to grounding

```xml
<task id="3.1" wave="3">
  <files>apps/api/app/agents/subagents/_base.py</files>
  <action>In the `assistant` node, read the tz off the already-computed `ctx` and pass it to `ground_current_date`. Change the call at ~line 111 from `ground_current_date(system)` to `ground_current_date(system, ctx.timezone if ctx is not None else None)`. `ctx` is already defined at line 98.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents -x</verify>
  <done>Node compiles; agent state/subagent tests pass; grounding receives tz when context has one.</done>
</task>
```

- [ ] **Step 1: Edit** `app/agents/subagents/_base.py` — the `bound.invoke([...])` block:

```python
        tz = ctx.timezone if ctx is not None else None
        response = bound.invoke(
            [
                system_with_summary(state, ground_current_date(system, tz)),
                *state["messages"],
            ]
        )
```

- [ ] **Step 2: Run the agent suite — expect PASS**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents -x`
Expected: existing `test_subagent_receives_todays_date_in_system_prompt` still passes (tz None → UTC path unchanged).

---

### Task 3.2 — Ground the supervisor's router

```xml
<task id="3.2" wave="3">
  <files>apps/api/app/agents/supervisor.py</files>
  <action>Move the `ctx` read to the top of the `supervisor` function (it is currently read only at ~line 90 for the tier gate) and reuse it. Wrap the router's system message with `ground_current_date(base, ctx.timezone)` at the `router.invoke` call (~line 74). Delete the now-duplicate `ctx = (...)` block at ~90-94 since `ctx` is defined above. Import `ground_current_date` from `app.agents.state` if not already imported.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents -x</verify>
  <done>Supervisor routing is date-grounded; tier-gate still uses the same ctx; agent tests pass.</done>
</task>
```

- [ ] **Step 1: Verify import** — ensure `app/agents/supervisor.py` imports `ground_current_date`. If the file imports `system_with_summary` from `app.agents.state`, add `ground_current_date` to that import.

- [ ] **Step 2: Edit the `supervisor` function** — restructure so `ctx` is read once, up top, and used for both grounding and the tier gate:

```python
    def supervisor(state: TravelAgentState, runtime: Runtime[AgentContext]) -> Command:
        logger.info("[agent] node=supervisor")
        ctx = (
            runtime.context
            if runtime is not None and runtime.context is not None
            else AgentContext()
        )
        established = state.get("language") or "unknown"
        base = SystemMessage(
            content=(
                f"{system.content}\n\n"
                f"Established conversation language: {established}; "
                "keep it unless the traveller clearly switches."
            )
        )
        intent = router.invoke(
            [system_with_summary(state, ground_current_date(base, ctx.timezone)), *state["messages"]]
        )
        target = getattr(intent, "target_agent", None)
        if target not in SUBAGENTS:
            logger.info("[agent] supervisor → END (unknown intent: %s)", target)
            return Command(
                update={
                    "messages": [
                        AIMessage(content="I'm not sure how to help with that yet.")
                    ]
                },
                goto=END,
            )
        # Tier gate (D.1): reuse the ctx read above.
        if ctx.allowed_subagents is not None and target not in ctx.allowed_subagents:
```

(Delete the old `ctx = ( runtime.context ... else AgentContext() )` block that previously sat just before the tier gate.)

- [ ] **Step 3: Run the agent suite — expect PASS**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents -x`

---

### Task 3.3 — Router reads + validates `body.timezone` and threads it

```xml
<task id="3.3" wave="3">
  <files>apps/api/app/routers/agent.py, apps/api/tests/api/agent/test_agent_timezone.py</files>
  <action>Add a `_resolve_timezone(raw)` helper that returns `raw` if it is a valid IANA name (via `zoneinfo.ZoneInfo`) else the `agent_timezone` default (log a warning, never raise). Add a `raw_timezone: str | None = None` param to `_resolve_context` and pass the resolved tz into `resolve_agent_context(..., timezone=...)`. Update BOTH call sites — `agent_chat` (~line 192) and `agent_stream` (~line 306) — to pass `raw_timezone=body.timezone`. `ZoneInfo`, `get_settings`, `logger` all need to be available (get_settings + logger already imported; add `from zoneinfo import ZoneInfo`).</action>
  <verify>cd apps/api && DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest tests/api/agent/test_agent_timezone.py -x</verify>
  <done>Valid tz reaches AgentContext.timezone; invalid/missing falls back to the configured default; no 422.</done>
</task>
```

- [ ] **Step 1: Write the failing test** — `apps/api/tests/api/agent/test_agent_timezone.py`

```python
from app.routers.agent import _resolve_timezone
from app.core.config import get_settings


def test_valid_timezone_passthrough():
    assert _resolve_timezone("Asia/Ho_Chi_Minh") == "Asia/Ho_Chi_Minh"


def test_invalid_timezone_falls_back_to_default():
    assert _resolve_timezone("Not/AZone") == get_settings().agent_timezone


def test_missing_timezone_falls_back_to_default():
    assert _resolve_timezone(None) == get_settings().agent_timezone
```

- [ ] **Step 2: Run it — expect FAIL** (`_resolve_timezone` undefined)

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_agent_timezone.py -x`

- [ ] **Step 3: Implement** — edit `app/routers/agent.py`. Add imports (top of file): `from zoneinfo import ZoneInfo` and ensure `get_settings` is imported from `app.core.config`. Add the helper above `_resolve_context`:

```python
def _resolve_timezone(raw: str | None) -> str:
    """Return a valid IANA tz string, falling back to the configured default.

    The client sends its detected timezone; a missing or invalid value must not
    fail the request — we ground dates against ``settings.agent_timezone`` instead.

    :param raw: Client-supplied IANA timezone name, or None.
    :return: A valid IANA timezone name.
    """
    default = get_settings().agent_timezone
    if not raw:
        return default
    try:
        ZoneInfo(raw)
        return raw
    except Exception:
        logger.warning("[agent] invalid timezone %r from client; using %s", raw, default)
        return default
```

Extend `_resolve_context`:

```python
def _resolve_context(
    effective_user_id: str,
    authenticated: bool,
    session: Session,
    raw_timezone: str | None = None,
) -> AgentContext:
```

and its return:

```python
    return resolve_agent_context(
        tier=tier,
        allow_reflection=allow_reflection,
        timezone=_resolve_timezone(raw_timezone),
    )
```

Update BOTH call sites to pass the request tz:

```python
    ctx = _resolve_context(uid, auth_user is not None, session, raw_timezone=body.timezone)
```

(One in `agent_chat` at ~line 192, one in `agent_stream` at ~line 306. `logger` and `get_settings` are already imported in the module; add `from zoneinfo import ZoneInfo`.)

- [ ] **Step 4: Run it — expect PASS**

Run: `cd apps/api && DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest tests/api/agent/test_agent_timezone.py -x`

---

### Task 4.1 — New prompt versions (planner v6, booking v5) + activate

```xml
<task id="4.1" wave="4">
  <files>apps/api/app/prompts/planner/v6.md, apps/api/app/prompts/booking/v5.md, apps/api/app/prompts/active.yaml</files>
  <action>Create planner v6 (from v5) and booking v5 (from v4) that REFRAME the "never guess dates" rule so resolving relative dates and stitching info given across turns are explicitly ALLOWED (state the assumption + confirm), while inventing a value never given stays forbidden. Reinforce confirm-then-call. Then bump active.yaml: `planner: 6`, `booking: 5`. This is the primary behavioral lever — see design §3.D. Requires a graph rebuild to take effect (Task 5.1).</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "from app.prompts.registry import registry; assert 'confirm' in registry.get('booking').lower(); assert registry.get('planner'); print('planner', 'booking loaded')"</verify>
  <done>active.yaml points planner→6, booking→5; registry loads both new versions.</done>
</task>
```

- [ ] **Step 1: Create** `app/prompts/planner/v6.md` — copy `planner/v5.md` verbatim, then replace the Guardrails date bullet (v5 lines 48-52) with:

```markdown
- **Before searching hotels, make sure you have the traveller's check-in and check-out
  dates, number of rooms, and number of guests (adults and children).** These must come
  from the traveller — never invent a value they never gave, and never fall back to a
  default party size.
- **Resolving is not guessing.** You DO have today's date (see CURRENT DATE in the system
  prompt). Resolve relative dates ("hôm nay"/"today", "ngày mai"/"tomorrow", "cuối tuần
  này"/"this weekend", "next Friday") to a concrete date yourself, and **combine details the
  traveller gave across several turns** (e.g. "10/07" in one message and "2026" in the next →
  10/07/2026). Do not re-ask for something already provided.
- **Confirm the resolved value once, then act.** When you inferred or resolved a date, restate
  the concrete date — including the number of nights the dates imply — and get a single yes/no
  confirmation before you search. Do not loop asking for the same field.
```

- [ ] **Step 2: Create** `app/prompts/booking/v5.md` — copy `booking/v4.md` verbatim, then (a) rewrite step 1 of "How to Work" and (b) replace the last Guardrail bullet:

Replace "How to Work" step 1 with:

```markdown
1. Check you have what the tool needs before calling it. For a **hotel** search or quote that
   means check-in and check-out dates, rooms, and guests (adults and children); for a **flight**
   it means the route and departure date. **Resolving is not guessing:** you have today's date
   (see CURRENT DATE in the system prompt) — resolve relative dates yourself and combine details
   the traveller gave across earlier turns rather than re-asking. When a detail only appeared
   earlier, or you resolved a relative/partial date, restate the concrete value — including the
   nights the hotel dates imply — and get a single yes/no confirmation before you call the tool.
   Only ask for a value the traveller genuinely never gave.
```

Replace the final Guardrail bullet ("Never guess dates, party size, or room count …") with:

```markdown
- **Never invent** a date, party size, or room count the traveller never gave. But resolving a
  relative date against today, and stitching values supplied across turns, is expected — not
  guessing. Confirm the resolved value once before booking.
```

- [ ] **Step 3: Edit** `app/prompts/active.yaml` — bump the two lines:

```yaml
planner: 6
booking: 5
```

- [ ] **Step 4: Verify the registry loads them**

Run: `cd apps/api && ../../.venv/bin/python -c "from app.prompts.registry import registry; print(registry.get('planner')[:40]); print(registry.get('booking')[:40])"`
Expected: prints the first line of each new version without error.

---

### Task 5.1 — Full suite + rebuilt-graph behavior check

```xml
<task id="5.1" wave="5">
  <files>apps/api/</files>
  <action>Run the whole BE suite on SQLite. Then, because the prompt + graph are baked at lifespan startup, rebuild the running dev graph and manually re-run the repro (Đà Nẵng→HCM "sáng mai", then split date across turns) to confirm the agent resolves + confirms + calls the tool instead of looping. Add a DeepEval case modeled on thread 7a22074c to app/eval/ (optional if the harness case format is ready).</action>
  <verify>cd apps/api && make test</verify>
  <done>Full suite green; manual repro no longer loops (agent resolves "sáng mai", stitches split dates, confirms once, calls search_flights).</done>
</task>
```

- [ ] **Step 1: Full suite** — `cd apps/api && make test` (SQLite, zero-config). Expected: all green.
- [ ] **Step 2: Rebuild the running graph** — prompt/graph are baked at startup and do NOT hot-reload (memory `prompt-changes-need-graph-rebuild-not-hot-reloaded`): `docker exec api-api-1 touch app/main.py` (or restart via `docker compose up -d` from `apps/api`).
- [ ] **Step 3: Manual repro** — in the web chat (or via `POST /agent/chat` with a `timezone`), send: "kiểm tra chuyến bay Đà Nẵng đi HCM sáng mai", then in later turns "10/07", "2026". Expected: the agent resolves "sáng mai" → tomorrow's date, stitches the split date, shows the concrete date, asks one yes/no confirm, then calls `search_flights` (a Flights panel appears). It must NOT re-ask for the year it was already given.
- [ ] **Step 4: (Optional) DeepEval case** — add a case mirroring the repro to `apps/api/eval/` per the existing harness format (memory `min-58-deepeval-eval-harness-shipped`); this is the only automated check for the LLM-behavior half.

---

### Task 5.2 — Frontend sends the detected timezone (cross-stack)

```xml
<task id="5.2" wave="5">
  <files>apps/web (agent chat/stream request builder)</files>
  <action>In apps/web, add `timezone: Intl.DateTimeFormat().resolvedOptions().timeZone` to the JSON body of the /agent/chat and /agent/stream requests. Without this the BE falls back to the configured default (Asia/Ho_Chi_Minh), so this task completes the end-to-end accuracy for non-VN users but is not required for the BE fix to work.</action>
  <verify>export PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" && cd apps/web && pnpm build</verify>
  <done>FE compiles; agent requests include a `timezone` field (verify in devtools Network tab).</done>
</task>
```

- [ ] **Step 1: Locate** the fetch/request builder that calls `/agent/chat` and `/agent/stream` in `apps/web` (search for `/agent/chat` or the SSE consumer). Use Node v24 for FE work.
- [ ] **Step 2: Add** `timezone: Intl.DateTimeFormat().resolvedOptions().timeZone` to the request body object(s).
- [ ] **Step 3: Verify** the field appears on the wire (browser devtools Network tab) and the build passes.

---

## Risks

- **Public-contract gate:** `ChatRequest.timezone` is additive/optional (superset) but trips `risk-corroboration.sh`. Authorize the commit with `RISK_WARN_CATEGORIES="public-contract"` (memory `public-contract-hard-gate`).
- **Weakening-validation gate:** editing `raise ToolException` lines in the tools + `resolve_travel_date` loosening `strptime` may warn; downgrade with `RISK_WARN_CATEGORIES` if it fires (memory `weakening-validation-gate-on-removed-assert`).
- **Graph rebuild required:** prompt (Task 4.1) + node changes only take effect after a graph rebuild; verify against a rebuilt graph, never the live container (Task 5.1 Step 2).
- **ruff-on-edit import stripping:** add each import together with a first usage in the same edit; run `ruff check --select F821` before tests (memory `ruff-on-edit-strips-unused-imports`).
- **Stale travel.db:** no schema change here, so no rebuild needed; but if the suite errors on load, rebuild `travel.db` (memory `stale-travel-db-breaks-suite-on-schema-change`).

## Status Log
- 2026-07-09 — Plan drafted from approved design + research brief. Awaiting review + execution-mode choice.
- 2026-07-09 — Executed waves 1–4 (subagent-driven): `25e9fed` (w1), `6935412` (w2), `d3c1ccd` (w3), `8d4aeb9` (w4), `a31a5e5` (active-versions test fix).
- 2026-07-09 — `/correctness-review`: findings #3 (YYYY/MM/DD) + #4 (bad-tz crash) fixed `fea3b06`; #1/#2 recorded advisory.
- 2026-07-10 — `/intent-review`: 3 findings recorded (`3b4f0d4`); clause-3 scope user-confirmed = collection-only (`ba69358`). All gates pass; 382 targeted tests green (CI-equivalent). Task 5.2 (FE tz) + 5.1 (manual/DeepEval acceptance) are documented follow-ups.
- 2026-07-10 — shipped via `feat/flight-search-date-context` (PR pending).
