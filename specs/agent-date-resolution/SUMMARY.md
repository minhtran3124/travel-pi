# agent-date-resolution — Summary

Lane: high-risk
Confidence: high
Reason: Four risk flags fire (public contract · existing behavior · weak proof · multi-domain) and the new `resolve_date` agent tool is additive client-visible surface (`/agent/manifest` + MCP tool list), so the public-contract gate applies — additive superset only, no route/envelope change.
Flags: public-contract (additive), existing-behavior, weak-proof, multi-domain
Affects: app/tools/registry.py (agent tool surface → /agent/manifest + MCP), app/core/dates.py, app/prompts/booking + supervisor
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> "now, i want to improve that agent dont need to ask the user to confirm about date time.
> But we need to find the way help to check the date/time correctly without any guess or pick random."

Two forks resolved by the user at intake (`AskUserQuestion`):

- **No-date case** — "Vẫn hỏi khi thiếu hẳn ngày": when the traveller gives *no* date signal at
  all, the agent still asks one question. Only the redundant *re-confirmation* of a date the agent
  already resolved is removed.
- **Correctness** — "Thêm tool resolve_date riêng, agent phải gọi trước": a dedicated deterministic
  tool computes the date (code, not LLM arithmetic) and the agent must call it before searching, so
  the resolution is verifiable in the tool trace.

## What changed

The agent no longer asks the traveller to confirm a date, and no longer computes one in its head.
`app/core/dates.py` now resolves the weekday and phrase forms it used to leave to the LLM (EN + VN,
diacritics optional), with pinned semantics and an `AmbiguousDateError` for anything that would need
a guess. A new read-only agent tool, `resolve_date`, wraps it: the agent passes the traveller's
literal expression, code computes the date, and the result lands in the tool trace where it can be
audited. `booking/v6` and the `ground_current_date` note then drop the pre-search confirmation — the
agent resolves, searches, and *states* the date in its answer so the traveller can correct it in one
turn. Two behaviors are deliberately preserved: explicit approval before an actual booking, and a
single question when the traveller gave no date at all (never a default, never a random pick).

### Rationale

The agent's date friction has two distinct causes and only one is a prompt problem. (1)
`app/prompts/booking/v5.md` step 1 orders a "single yes/no confirmation before you call the tool" —
that is a confirmation turn before a *search/quote*, which is pure friction. (2) `app/core/dates.py`
deliberately does **not** parse weekday/phrase forms ("next Friday", "cuối tuần này"), leaving that
arithmetic to the LLM where nothing can check it — that is the "guess" the user wants eliminated.
Fixing only the prompt would remove the ask while leaving the unverifiable arithmetic in place, so
both are addressed: `resolve_date` makes the computation deterministic and auditable in the tool
trace, and the prompt then trusts it instead of asking the human to double-check the model's math.
Approval before an actual **booking** is untouched — that gate is about money, not about dates.

### Alternatives considered

- **Date-less / range search** (browse a 7-day window, let the traveller pick) — rejected by the
  user at intake; keeps the "still ask when no date at all" semantics instead.
- **Publicly-stated default date** (e.g. assume today, say so) — deterministic but still chooses for
  the traveller; rejected at intake.
- **Prompt-only fix** (drop the "ask" rule, keep LLM date math) — cheapest, but it is exactly the
  unverifiable guessing the request asks to remove.
- **Extend `resolve_travel_date` in-place without a tool** — the resolution would stay invisible to
  the trace; the user explicitly chose the callable tool for auditability.

### Deviations

- Rule 1 (task 2.1) — `resolve_date` declares an explicit `args_schema=ResolveDateArgs` rather than
  the inline `Annotated`/`Field` form the plan asked for. The "explicit args_schema breaks LangGraph
  injection" rule only bites tools that take `InjectedState`/`InjectedStore` args; `resolve_date`
  takes none, and the pre-existing registry contract test
  (`tests/tools/test_tool_registry.py::test_every_tool_has_explicit_described_schema`) *requires* a
  hand-authored schema for every non-injected tool — the inline form would have broken it.
  Corroborated: that test passes 40/40 with `resolve_date` registered. `app/tools/date_tools.py`.
- Rule 1 (task 3.2) — `ground_current_date` also lost its middle sentence ("Resolve every relative
  date … against it"), not just the closing "ask them" one the plan named. Keeping it would have left
  the grounded prompt self-contradictory: compute the date yourself *and* route it through
  `resolve_date`. `app/agents/state.py`.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Resolver unit (task 1.1) | `cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_dates.py -q` | 0 | 51 passed |
| Resolver lint (task 1.1) | `cd apps/api && ruff check app/core/dates.py tests/core/test_dates.py` | 0 | clean |
| Resolver spot-check vs a known Saturday (today = Sat 2026-07-11) | ad-hoc REPL over 18 expressions | 0 | "thứ 6 tuần sau"→2026-07-24(Fri) · "friday"→07-17 · "thứ 7"→07-18 (strictly-future) · "cuối tuần này"→07-18(Sat) · "tuần sau"→07-13(Mon) · "3 ngày nữa"→07-14 · "sometime soon"/"07/2026"→AmbiguousDateError |
| Tool + registry (task 2.1) | `pytest tests/api/tools/test_date_tools.py tests/api/agent -q` | 0 | 99 passed; registry contract `tests/tools/test_tool_registry.py` 40/40 |
| `resolve_date` live invoke (task 2.1) | ad-hoc REPL | 0 | bound to planner/concierge/booking, readOnly; "thứ 6 tuần sau"→`2026-07-24 (Friday). Today is 2026-07-11 (Asia/Ho_Chi_Minh).`; "khi nào rảnh thì đi"→ToolException telling the agent to ask |
| Prompt booking v6 (task 3.1) | `pytest tests/api/agent tests/agents -q` | 0 | 214 passed; v5→v6 diff reviewed — booking-approval guardrails byte-identical |
| Grounding note (task 3.2) | `pytest tests/agents/test_state.py -q` | 0 | 14 passed |
| Tool error text (task 3.3) | `pytest tests/api/tools -q` | 0 | 14 passed; diff inspected — docstring/message lines only, no validation branch touched |
| Full suite (task 4.1) | `cd apps/api && mv .env .env.bak && DATABASE_URL=sqlite:///./full.db ../../.venv/bin/python -m pytest -q; mv .env.bak .env` | 0 | **1486 passed**. The repo `.env` must be set aside — it pins a real Postgres/OpenAI/ORS config that fails 5 unrelated tests regardless of this diff (known: `env-openai-key-test-breaks-llm-tests`) |
| Lint (task 4.1) | `cd apps/api && ruff check app scripts` | 0 | clean |
| **Live: weekday date → no question** (task 4.1) | `POST /agent/chat {"message":"tìm chuyến bay SGN đi HAN thứ 6 tuần sau"}` on a fresh thread, after `docker exec api-api-1 touch app/main.py` | 0 | Tool trace: `resolve_date` → `search_flights`. Reply: "chuyến bay **SGN → HAN** vào **24/07/2026** (thứ Sáu tuần sau)" — resolved, searched, stated. No confirmation turn. 24/07 is the correct answer for today = Sat 2026-07-11 |
| **Live: relative date → no question** (task 4.1) | `POST /agent/chat {"message":"tìm chuyến bay SGN đi HAN ngày mai"}` | 0 | Tool trace: `resolve_date` → `search_flights`. Reply states **12/07/2026** |
| **Live: no date → asks exactly once** (task 4.1) | `POST /agent/chat {"message":"tìm chuyến bay SGN đi HAN"}` | 0 | No search tool called. Reply: "bạn chưa nói **ngày bay** … Bạn muốn bay **ngày nào**?" — one question, no default date |

### Rollback

- Revert code: `git revert <sha>`
- Prompt rollback is independent of code: set `booking`/`supervisor` back to their prior versions in
  `app/prompts/active.yaml` (versioned prompts, old files retained) and rebuild the graph.

### Harness-Delta

- backlog (→ `/compound`) — **A prompt-behavior change needs a live probe in its `<verify>`, not just
  pytest.** Task 3.2's rewrite of `ground_current_date` passed every test (14/14) while silently
  dropping the "do not guess or invent one" prohibition: the note still *permitted* asking but no
  longer *forbade* defaulting, and the live agent promptly defaulted to today when given no date —
  the exact behavior the plan lists as a non-goal. Only the task-4.1 live probe caught it. A prompt
  assertion (`"resolve_date" in note`) proves a string is present, never that a behavior survived.
- backlog — **Task `<verify>` scopes were too narrow to catch a cross-cutting pin.** Task 3.1 bumped
  `active.yaml` and verified with `pytest tests/api/agent tests/agents`, which does not include
  `tests/prompts/` — where `test_min53_bumped_versions_active` pins the active version numbers. The
  break only surfaced in the wave-4 full suite. A task that edits `active.yaml` should verify
  `tests/prompts/` too.
- note — `hooks/blast-radius-check.sh` cited a stale active plan (`specs/min-54-chat-ui-polish/PLAN.md`)
  on every edit in this feature, and `hooks/risk-corroboration.sh` picked the most-recently-modified
  `specs/*/SUMMARY.md` (`ls -t`) rather than this feature's, blocking a commit against another spec's
  `Lane: normal`. Both are plan-selection bugs, not scope violations. Workaround used: stage this
  feature's `SUMMARY.md` in the commit (the hook prefers a staged SUMMARY).
