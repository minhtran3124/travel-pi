---
slug: flight-search-date-context
status: proposed
owner: Minh Tran
created: 2026-07-09
---

# Flight & Hotel Search — Date Awareness + Multi-Turn Info Stitching

## 1. Problem & Goal

The agent fails to collect flight-search info even when the traveller supplies it.
Reproduced live in conversation `7a22074c-4611-4690-8b64-b24856a52ef4`:

- User: *"chuyến bay Đà Nẵng đi HCM **sáng mai**"* → agent demands a concrete date
  (never resolves the relative date).
- User: *"10/07"* → agent demands the **year**.
- User: *"2026"* → agent replies it *"only has the year 2026"* and refuses — it **dropped
  "10/07" from the previous turn**. No flight tool was ever called (all `tool_calls` NULL).

Three defects behind this:

1. **Relative dates not resolved** — "sáng mai" / "ngày mai" / "tomorrow" never become an ISO date.
2. **No multi-turn stitching** — info supplied across adjacent turns ("10/07" then "2026") is not combined.
3. **UTC-only "today"** — `ground_current_date()` uses UTC; a Vietnam (UTC+7) user near midnight sees an off-by-one date.

**Goal:** for both **flight** and **hotel** info-collection, resolve relative/partial dates
against the correct local "today", stitch info from recent turns, confirm the resolved
concrete date once, then call the tool — instead of looping on questions the user already answered.

**Non-goals:** no changes to other sub-agents (concierge/journal/budget); no change to the
deterministic flight/hotel generation algorithm; no new external provider; no persistence of
timezone in the DB.

## 2. Key Finding (why "just inject the date" is not the fix)

Date grounding **already exists**: `ground_current_date()` (`app/agents/state.py:79-100`)
prepends a `SystemMessage` ("today is …, resolve every relative date against it") into every
sub-agent's `assistant` node (`app/agents/subagents/_base.py:111`). Full verbatim history is
also passed on every model call (`_base.py:112-113`). So the gap is between the *injected date*
and the model's *actual tool use*, compounded by a prompt instruction — `"Never guess dates …
these come from the traveller"` (`app/prompts/booking/v4.md:27`) — that the model appears to
read as "don't infer / don't resolve / don't stitch". The fix is **defense-in-depth (Hybrid)**,
not a single injection.

## 3. Architecture — 4 components

### A. Timezone plumbing (new)
- **FE** sends `timezone` (IANA name from `Intl.DateTimeFormat().resolvedOptions().timeZone`,
  e.g. `"Asia/Ho_Chi_Minh"`) in the body of every `/agent/chat` and `/agent/stream` call.
- **BE** adds an optional, additive field `timezone: str | None = None` to `ChatRequest`
  (`app/schemas/agent.py:16`). The router validates it via `zoneinfo.ZoneInfo(tz)`; missing or
  invalid → fallback to config default (log a warning, never error).
- **New config**: add `agent_timezone: str = "Asia/Ho_Chi_Minh"` to `app/core/config.py`
  (there is no such default today) as the fallback.
- **Threading interface (the key integration point):** router resolves the effective tz string →
  places it on `AgentContext` (new field `timezone: str`, `app/agents/context.py`) → the context is
  already carried into graph state, so the assistant node reads `state`'s context tz and passes it
  to `ground_current_date(base, tz)`. The supervisor reads the same context tz. No new state channel
  is introduced; tz rides the existing `AgentContext`.

### B. Date grounding (fix)
- Add an **additive** timezone parameter to the existing helper — real signature today is
  `ground_current_date(base: SystemMessage)` (`state.py:79`), currently building "today" from
  `datetime.now(timezone.utc)` (`state.py:92`). Change it to `ground_current_date(base, tz)` and
  compute "today" in `tz`. This touches the one existing call site (`_base.py:111`) — it is an
  added argument, **not** a rename.
- Ground the date for the **supervisor** too — `app/agents/supervisor.py:74` currently calls
  `system_with_summary(state, base)` without `ground_current_date`, so routing is date-blind. Add
  the grounding call there (new call site).

### C. Deterministic date normalization in tools (new)
- New helper `resolve_travel_date(raw: str, today: date) -> str` in a new `app/core/dates.py`.
  **Scope of this helper is a deterministic safety net for the common simple forms only:**
  relative ("ngày mai"/"tomorrow"/"hôm nay"/"today"), partial ("10/07" → DD/MM, VN convention),
  and full ("10/07/2026", ISO). Returns `YYYY-MM-DD`. Missing year → nearest **future** occurrence.
  Unparseable or past-after-resolution → raise `ToolException` with the guidance style already in
  `flight_tools.py:89-100`.
- **Division of labour (resolves the "next Friday" question):** richer natural-language dates
  ("next Friday", "cuối tuần này", "thứ Sáu tới") are resolved by the **LLM** against the grounded
  CURRENT DATE (the prompt note at `state.py:95` already promises this) and reach the tool as ISO.
  `resolve_travel_date` does **not** attempt weekday/phrase parsing — it only backstops the simple
  relative/partial forms the model most often fumbles. No contradiction between the two layers.
- `app/tools/flight_tools.py` (departure_date) and the hotel search/quote tool (check-in/out)
  call `resolve_travel_date` before the existing ISO `strptime`. Even if the LLM passes "ngày mai"
  or "10/07", the tool resolves it deterministically.

### D. Prompt hardening (new registry versions — require graph rebuild)
**Important:** the current prompts (`booking/v4.md:16-18`, `planner/v5.md:48-52`) *already*
instruct the model to restate details supplied earlier and to confirm before calling a tool. So
defect #2 is **not a missing instruction** — the model *ignores* an existing one, because it is
in direct tension with the nearby absolute rule `"Never guess dates … these come from the
traveller"` (`booking/v4.md:27`) and resolves the conflict by refusing. **The lever is removing
the contradiction, not adding more stitch text.** New `planner` and `booking` versions therefore:
1. **Reframe `never guess dates`** so the model does not read resolution/stitching as guessing:
   explicitly permit *inferring a concrete date from what the traveller already said* (relative or
   split across turns) — state the assumption — while still forbidding *inventing* a value they
   never gave. This is the primary change.
2. Keep (and slightly sharpen) the existing **stitch** rule: never drop a field given in an
   earlier turn; restate the running set of collected fields each turn.
3. **Confirm-then-call** (see §6): show the resolved concrete date and get one yes/no confirmation
   before calling the tool — reinforcing the existing pattern (`booking/v4.md:18`, `planner/v5.md:52`).
- Activate the new versions via the prompt registry `active` pointer; the running graph is baked at
  lifespan startup, so a rebuild is required (see §8).

## 4. Data flow

```
FE (Intl tz)
  → POST /agent/chat|stream { message, timezone }
  → router: validate tz (zoneinfo) | fallback Asia/Ho_Chi_Minh
  → AgentContext.timezone → state
  → assistant node: ground_current_date(tz) prepends "today is <date in tz>"
  → LLM: resolve relative/partial date + stitch fields from recent turns
  → LLM: show resolved concrete date, ask one yes/no confirm  ← §6 (ii)
  → on confirm: call flight/hotel tool(departure_date=…)
  → resolve_travel_date() normalizes to ISO against today(tz)
  → deterministic search
```

## 5. Error handling
- Invalid/missing tz from FE → fallback default, log warning, never error.
- Date still unparseable by the tool → `ToolException` with guidance (existing pattern preserved).
- Past date after resolution → `ToolException` (now correct because tz-aware).

## 6. Confirmation UX — decision: (ii) confirm-first
When the traveller gives a relative/partial date, the agent **resolves it to a concrete date,
shows it, and asks a single yes/no confirmation before calling the tool** — e.g.
*"Bạn muốn bay sáng mai **10/07/2026** đúng không?"*. This is **not** re-asking for info already
supplied (the bug); it confirms the *resolved value*. It aligns with the existing prompt rule to
confirm before tool calls (`booking/v4.md:18`, `planner/v5.md:52`), and adds safety against a
wrong DD/MM or year-rollover inference.

## 7. Testing

**Deterministic unit tests**
- `resolve_travel_date`: "ngày mai", "tomorrow", "hôm nay", "10/07", "10/07/2026", ISO,
  past date → raises, invalid → raises, year rollover (Dec → Jan picks next year). Weekday/phrase
  forms ("next Friday") are **out of scope for the helper by design** (§3.C division of labour —
  the LLM resolves those to ISO); assert the helper raises/passes-through cleanly on such input
  rather than mis-parsing it.
- `ground_current_date(tz)`: midnight-boundary UTC vs `Asia/Ho_Chi_Minh` (asserts local date);
  invalid tz → fallback default.
- `ChatRequest`: accepts `timezone`, omits it (None), invalid value handled at router (fallback).

**Behavior (LLM) verification**
- Multi-turn stitching and confirm-first flow are LLM behaviors → verified via the DeepEval
  harness (`apps/api/eval/`) with a case modeled on the repro thread, plus a manual re-run.
  These are not deterministic unit tests (FakeLLM returns canned replies).

## 8. Risks
- **Public-contract touch**: adding `timezone` to `ChatRequest` is an additive optional field
  (backward-compatible superset), but still trips the public-contract gate at commit — authorize
  per `public-contract-gate-warn-only` / `RISK_WARN_CATEGORIES`.
- **Weakening-validation gate**: making the tool accept more date forms may look like loosening
  validation (`resolve_travel_date` vs the strict `strptime`) — corroboration hook may warn.
- **Prompt/graph rebuild**: new prompt versions do not hot-reload — the running graph is baked at
  lifespan startup (`prompt-changes-need-graph-rebuild-not-hot-reloaded`); verify against a rebuilt
  graph, and flip the registry `active` pointer.
- **DD/MM ambiguity**: "10/07" assumes DD/MM (VN). Confirm-first (§6) mitigates a wrong guess.

## 9. Status Log
- 2026-07-09 — Design approved (scope: flight + hotel; approach: Hybrid; timezone: FE per-request
  detect w/ fallback; UX: (ii) confirm-first). Next: spec review → xia2 → writing-plans.
