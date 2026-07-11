---
slug: agent-date-resolution
status: proposed
owner: Minh Tran
created: 2026-07-11
---

# Deterministic date resolution — stop asking the traveller to confirm a date we can compute

## 1. Motivation

Today the agent does two things the traveller experiences as friction and we cannot audit:

1. **It asks for confirmation of a date it already resolved.** `app/prompts/booking/v5.md` step 1
   orders "restate the concrete value … and get a single yes/no confirmation **before you call the
   tool**". That is a confirmation turn before a *search or quote* — not before a booking.
2. **It does the date arithmetic itself.** `app/core/dates.py` deliberately parses only the simple
   forms (ISO · today/tomorrow · `DD/MM[/YYYY]`) and leaves weekday/phrase forms ("next Friday",
   "cuối tuần này", "thứ 6 tuần sau") to the LLM, where nothing checks the result. `ground_current_date`
   (`app/agents/state.py:80`) grounds "today" and then tells the model to *ask* when it cannot derive
   a date — so an LLM slip is invisible and the safe fallback is another question.

The fix is to make the computation deterministic and visible in the tool trace, then let the prompt
trust it. **Resolving is not guessing; asking to double-check the model's arithmetic is not safety.**

## 2. Non-goals

- **Do not remove booking approval.** The explicit yes/no before `book_flight` / `book_hotel` stays —
  that gate is about money, not about dates. Only the pre-*search*/pre-*quote* date confirmation goes.
- **Do not invent a date when the traveller gave no date signal at all.** Decided at intake: the agent
  still asks exactly one question in that case. No default date, no random pick, no range search.
- **Do not resolve genuinely ambiguous forms by convention.** An ambiguous input must raise, not guess.
- No per-request timezone plumbing into tools. Tools ground "today" on `settings.agent_timezone`
  (as `search_flights` already does); the prompt uses `ctx.timezone`. Unifying those is out of scope.

## 3. Success Criteria

- A traveller who says "bay ngày mai" / "next Friday" gets **results**, not a confirmation question.
- Every non-ISO date the agent uses was computed by `resolve_date` and is visible in the tool trace.
- An ambiguous or absent date still produces exactly one question — never a fabricated date.
- Full suite green; `resolve_date` appears in `/agent/manifest` and over MCP (additive only).

## 4. Tasks

### Task 1.1 — Deterministic resolver: weekday + phrase forms, ambiguity raises

```xml
<task id="1.1" wave="1">
  <files>app/core/dates.py, tests/core/test_dates.py</files>
  <action>Extend resolve_travel_date to cover the forms the LLM is currently left to compute, keeping every existing form working unchanged. Add, case-insensitively, EN + VN (with and without diacritics): weekday names (monday…sunday, thứ hai…chủ nhật, thu 2…cn), optionally prefixed by this/next ("next friday", "thứ 6 tuần sau", "thứ 6 tuần này"); "next week"/"tuần sau" (→ Monday of next week); "this weekend"/"cuối tuần này" (→ the coming Saturday); and day offsets ("in 3 days", "3 ngày nữa"). Semantics, documented in the docstring and pinned by tests: a BARE weekday or a "this"-prefixed weekday resolves to the next occurrence strictly AFTER today (never today itself, never the past); a "next"-prefixed weekday resolves to that same occurrence plus 7 days. Raise AmbiguousDateError (new, subclassing ValueError so existing except-ValueError callers keep working) for input that cannot be resolved without guessing — an unrecognized phrase, or a bare month/year with no day. Never silently pick a value. Do NOT change the existing ISO / relative-day-word / DD-MM branches or their tests.</action>
  <verify>cd apps/api &amp;&amp; ../../.venv/bin/python -m pytest tests/core/test_dates.py -q</verify>
  <done>New forms resolve deterministically; ambiguous input raises AmbiguousDateError; all pre-existing test_dates.py cases still pass.</done>
</task>
```

### Task 2.1 — `resolve_date` tool + registry wiring

```xml
<task id="2.1" wave="2">
  <files>app/tools/date_tools.py, app/tools/registry.py, tests/api/tools/test_date_tools.py</files>
  <action>Add app/tools/date_tools.py exposing a single read-only tool `resolve_date(expression: str)` that grounds today via today_in_timezone(get_settings().agent_timezone), calls resolve_travel_date, and returns a summary string carrying the ISO date, its weekday, and the grounded today — e.g. "2026-07-17 (Friday). Today is 2026-07-11 (Asia/Ho_Chi_Minh)." — so the resolution is auditable in the tool trace. On AmbiguousDateError raise ToolException whose message names the ambiguity and instructs the agent to ask the traveller for a concrete date (this is the ONLY path that leads to a question). Follow the file conventions of flight_tools.py: module docstring, log_tool_call, Field descriptions written for the model, and a DATE_TOOLS list. Do NOT pass an explicit args_schema — describe args inline via Annotated/Field (see docs/solutions: an explicit args_schema breaks LangGraph injection). Export DATE_TOOLS from registry.py and add it to the planner, concierge, and booking domains (the three that call dated search tools). readOnly=True falls out of the existing _meta default — do not touch _WRITE/_DESTRUCTIVE.</action>
  <verify>cd apps/api &amp;&amp; ../../.venv/bin/python -m pytest tests/api/tools/test_date_tools.py tests/api/agent -q</verify>
  <done>resolve_date resolves relative/weekday input, raises a clear ToolException on ambiguity, and is bound to planner/concierge/booking; agent manifest tests still pass.</done>
</task>
```

### Task 3.1 — Prompt: booking v6 (stop confirming dates before a search)

```xml
<task id="3.1" wave="3">
  <files>app/prompts/booking/v6.md, app/prompts/active.yaml, app/prompts/CHANGELOG.md</files>
  <action>Copy booking/v5.md to v6.md and change ONLY the date-confirmation behavior. In step 1: drop "and get a single yes/no confirmation before you call the tool" for searches and quotes. Replace it with: any date the traveller expresses in a non-ISO form (relative, weekday, partial) MUST be sent through the resolve_date tool — never compute a date yourself; then search straight away and STATE the resolved date in the answer ("Chuyến bay thứ Sáu 17/07…") so the traveller can correct it, rather than asking them to pre-approve it. Ask for a date ONLY when the traveller has given no date signal at all, or resolve_date reports the expression is ambiguous. Leave the booking-approval guardrails intact and untouched: "Never confirm a booking without explicit approval" and the explicit yes/no before book_* stay exactly as they are — this task removes a pre-SEARCH confirmation, not the pre-BOOKING one. Bump booking to 6 in active.yaml and add a CHANGELOG entry. Note active.yaml is the pointer that actually selects the version (see docs/solutions/agent/supervisor-active-yaml-is-a-pointer.md) — editing the .md alone is a silent no-op.</action>
  <verify>cd apps/api &amp;&amp; ../../.venv/bin/python -m pytest tests/api/agent tests/agents -q</verify>
  <done>booking v6 is active; it mandates resolve_date and states the resolved date instead of asking; booking approval language is byte-identical to v5's.</done>
</task>
```

### Task 3.2 — Grounding note: point at the tool instead of at a question

```xml
<task id="3.2" wave="3">
  <files>app/agents/state.py, tests/agents/test_state.py</files>
  <action>In ground_current_date, keep the CURRENT DATE grounding and the "never pass a tool a date earlier than today" rule, but replace the closing sentence "If the traveller has not given enough to derive a concrete date, ask them — do not guess or invent one." with guidance matching the new tool: relative, weekday, or partial dates must be resolved with the resolve_date tool rather than computed in your head; do not ask the traveller to confirm a date resolve_date already returned — state it in your answer so they can correct it; ask only when they gave no date signal at all or resolve_date reports the expression is ambiguous. Update the docstring and the affected assertions in tests/agents/test_state.py.</action>
  <verify>cd apps/api &amp;&amp; ../../.venv/bin/python -m pytest tests/agents/test_state.py -q</verify>
  <done>The grounded system message routes relative dates to resolve_date and no longer instructs the model to ask for a date it can resolve.</done>
</task>
```

### Task 3.3 — Align the search tools' error messages with the new path

```xml
<task id="3.3" wave="3">
  <files>app/tools/flight_tools.py, app/tools/hotel_tools.py</files>
  <action>The ToolException messages raised when departure_date / check_in / check_out fail to resolve currently end with "ask the traveller for a concrete date" and "confirm the traveller's intended date". Reword them to route through the new tool first: instruct the agent to call resolve_date on the traveller's original expression, and to ask the traveller only if resolve_date reports it ambiguous. Keep the existing resolve_travel_date backstop call and all validation behavior (past-date rejection, the one-day timezone tolerance) exactly as-is — this is a message-only change.</action>
  <verify>cd apps/api &amp;&amp; ../../.venv/bin/python -m pytest tests/api/tools -q</verify>
  <done>Tool error text points the agent at resolve_date; no validation or resolution behavior changed.</done>
</task>
```

### Task 4.1 — Full suite + live behavior check

```xml
<task id="4.1" wave="4">
  <files>specs/agent-date-resolution/SUMMARY.md</files>
  <action>Run the full backend suite. Then verify the actual product behavior against the running docker agent (prompt/registry changes are baked at lifespan — force a rebuild with `docker exec api-api-1 touch app/main.py` first, per docs/solutions): send "tìm chuyến bay SGN đi HAN thứ 6 tuần sau" on a FRESH thread_id and confirm the agent (a) calls resolve_date, (b) searches without asking a confirmation question, (c) states the resolved date in its reply. Send "tìm chuyến bay SGN đi HAN" (no date signal) and confirm it still asks exactly one question. Record both transcripts and the suite result in SUMMARY.md ### Verify.</action>
  <verify>cd apps/api &amp;&amp; make test</verify>
  <done>Full suite green; both live transcripts recorded in SUMMARY.md — resolved-date path asks nothing, no-date path asks once.</done>
</task>
```

## 4b. Phase 5 — Replace the word dictionaries with an LLM parser (follow-up)

**Why.** Waves 1–4 shipped a hardcoded lexicon (`_RELATIVE_DAYS`, `_WEEKDAY_NAMES`, this/next
prefix tables). It is a treadmill: `"tuần tới"` — as ordinary as `"tuần sau"` — was missing, so the
agent asked about a phrase that was never ambiguous. Patching it word by word never converges, and
it only ever covers the two languages we thought of.

**The split.** Understanding language is what an LLM is good at; date arithmetic is what it is bad
at — the P0 (`+7` overshoot) was arithmetic. So: **the model parses, the code computes.** The model
returns a *structured intent* (`{kind: "weekday", weekday: "monday", week: "next"}`), never a date.
Code turns that intent into an ISO date deterministically. A misread phrase is visible in the trace
and testable; a wrong `+7` becomes impossible.

### Task 5.1 — Prompt + model wiring for the date parser

```xml
<task id="5.1" wave="5">
  <files>app/prompts/date_resolution/v1.md, app/prompts/active.yaml, app/prompts/CHANGELOG.md, app/agents/constants.py, app/data/agent_config.py</files>
  <action>Add the `date_resolution` prompt family: a system prompt that receives today's date, weekday, and IANA zone, and must return a STRUCTURED INTENT — never a computed date. Cover, with few-shot examples in several languages (VN with/without diacritics, EN, and at least one the lexicon never handled, e.g. 来週の月曜日 / próximo lunes), each intent kind: absolute (explicit d/m[/y]), relative_day (today/tomorrow/day-after), weekday + week(current|next), week_start, weekend + week, offset (N days), and ambiguous (with a reason). State the pinned conventions the model must map onto — a bare weekday means the next occurrence strictly after today; "this <weekday>" means the current calendar week; "next <weekday>" means the next calendar week — and that anything it cannot map without inventing information is `ambiguous`, which is what makes the agent ask. Register it in active.yaml (`date_resolution: 1`) + CHANGELOG. Add "date_resolution" to FAST_AGENTS (app/agents/constants.py) so it resolves to the cheap model, and to AGENT_CONFIG_NODES + AGENT_DESCRIPTIONS (app/data/agent_config.py) so it is configurable from the dashboard like every other model.</action>
  <verify>cd apps/api &amp;&amp; mv .env .env.bak; DATABASE_URL=sqlite:///./s.db ../../.venv/bin/python -m pytest tests/prompts tests/api/prompts -q; r=$?; mv .env.bak .env; rm -f s.db; exit $r</verify>
  <done>registry.get("date_resolution") returns the prompt; it resolves to the fast model; dashboard config lists it.</done>
</task>
```

### Task 5.2 — `core/dates.py`: numeric fast-path + intent arithmetic, dictionaries deleted

```xml
<task id="5.2" wave="5">
  <files>app/schemas/date_intent.py, app/core/dates.py, tests/core/test_dates.py</files>
  <action>Define the DateIntent Pydantic schema (the contract the model fills). Rewrite core/dates.py to two language-independent halves: (a) `parse_numeric_date(raw, today)` — ISO, DD/MM, DD/MM/YYYY, YYYY/MM/DD only, no words; (b) `compute_from_intent(intent, today)` — the deterministic arithmetic, carrying forward the week-anchored semantics and every invariant already pinned by the current tests (bare weekday = strictly after today; "next <weekday>" = that weekday of next calendar week, always inside the window opened by week_start(next); weekend = Saturday, or today when the weekend is already underway; offsets bounded to 0..730; nothing resolves into the past). DELETE _RELATIVE_DAYS, _WEEKDAY_NAMES, the this/next prefix + suffix tables, the day-offset regexes, and the diacritic folding — every word-matching table goes. Keep AmbiguousDateError and today_in_timezone. Tests stay pure (no LLM): keep the 7-anchor sweep and the cross-form invariant, re-expressed over intents.</action>
  <verify>cd apps/api &amp;&amp; ../../.venv/bin/python -m pytest tests/core/test_dates.py -q &amp;&amp; ruff check app/core</verify>
  <done>No word table remains in core/dates.py; the arithmetic invariants still hold across all 7 anchors.</done>
</task>
```

### Task 5.3 — `resolve_date` calls the parser, code computes

```xml
<task id="5.3" wave="6">
  <files>app/tools/date_tools.py, tests/api/tools/test_date_tools.py</files>
  <action>Rewrite resolve_date: (1) try parse_numeric_date — an ISO/DD-MM date costs zero tokens and zero latency; (2) otherwise call the LLM: `get_agent_llm("date_resolution").with_structured_output(DateIntent, method="function_calling")` (copy supervisor.py:57 — the function_calling method is deliberate), system = registry.get("date_resolution") with today/weekday/zone interpolated, human = the traveller's literal expression; (3) compute the date IN CODE from the returned intent — never take a date from the model; (4) apply the existing past-date guard and return the same summary string. kind == "ambiguous" -> ToolException carrying the model's reason (the only path that makes the agent ask). Any LLM/parse failure -> ToolException, never a raw exception. Tests: monkeypatch get_agent_llm to a FakeLLM(structured_responses=[...]) — the seam used by tests/api/tools/test_date_tools.py:21 — and cover: numeric fast-path takes ZERO LLM calls; a parsed intent computes the right date; ambiguous -> ToolException; past -> ToolException; an LLM exception -> ToolException, not a crash.</action>
  <verify>cd apps/api &amp;&amp; mv .env .env.bak; DATABASE_URL=sqlite:///./s3.db ../../.venv/bin/python -m pytest tests/api/tools tests/tools/test_tool_registry.py -q; r=$?; mv .env.bak .env; rm -f s3.db; exit $r</verify>
  <done>resolve_date resolves any language via the model but computes every date in code; no LLM call for numeric input; tests run offline on FakeLLM.</done>
</task>
```

### Task 5.4 — The search tools' backstop is numeric-only now

```xml
<task id="5.4" wave="6">
  <files>tests/api/tools/test_flight_tools_dates.py, tests/api/tools/test_hotel_tools_dates.py</files>
  <action>search_flights/search_hotels still call resolve_travel_date as a backstop, but it no longer understands words — so a word expression passed straight to a search tool now raises ToolException telling the agent to call resolve_date first. That is the intended tightening: nothing previously FORCED the resolve_date round-trip the audit trail depends on, and now something does. Update the tests that pass "tomorrow"/relative words directly to a search tool: assert the ToolException and that its message names resolve_date, instead of asserting a silent resolution. Keep every numeric/ISO case passing unchanged, and keep the past-date + one-day-timezone-grace tests exactly as they are.</action>
  <verify>cd apps/api &amp;&amp; mv .env .env.bak; DATABASE_URL=sqlite:///./s4.db ../../.venv/bin/python -m pytest tests/api/tools -q; r=$?; mv .env.bak .env; rm -f s4.db; exit $r</verify>
  <done>Word input to a search tool fails loudly toward resolve_date; numeric input still resolves.</done>
</task>
```

### Task 5.5 — Full suite + multilingual live probe

```xml
<task id="5.5" wave="7">
  <files>specs/agent-date-resolution/SUMMARY.md</files>
  <action>Full suite + ruff. Then rebuild the graph (`docker exec api-api-1 touch app/main.py`) and probe on FRESH thread_ids, checking the tool trace each time: "thứ 2 tuần tới" (the phrase that regressed), "thứ 6 tuần sau" (must be the Friday of next week, NOT +7), "next friday", a language the lexicon never covered, and a no-date message (must still ask exactly one question). Record every transcript, the resolved date, and the tool trace in SUMMARY.md ### Verify.</action>
  <verify>cd apps/api &amp;&amp; make test</verify>
  <done>Suite green; the probes show correct dates across languages with resolve_date -> search_flights in every trace, and no-date still asks once.</done>
</task>
```

## 5. Risks

- **Weekday semantics are a convention, not a fact.** "Thứ 6" on a Friday could mean today or next
  week. Task 1.1 pins one rule (strictly-future) and documents it; anything outside the pinned set
  raises rather than guesses. If the convention proves wrong in use, it is one constant to change.
- **Prompt edits are silent no-ops without `active.yaml`** and are not hot-reloaded (graph is baked at
  lifespan). Both are called out in the task actions; task 4.1 verifies against a rebuilt container.
- **Additive public surface.** `resolve_date` appears in `/agent/manifest` and over MCP. Additive
  superset only — no route, method, or envelope change. The public-contract gate may need
  `RISK_WARN_CATEGORIES="public-contract"` at commit time.
- **Removing a confirmation reduces a safety net.** Mitigated by making the agent *state* the resolved
  date in its answer (correctable in one turn) and by leaving booking approval untouched.

## 6. Status Log

- 2026-07-11 — plan drafted; intake recorded (high-risk lane, high confidence, no escalation).
