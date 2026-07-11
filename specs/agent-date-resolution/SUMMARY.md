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
| ~~Resolver spot-check vs a known Saturday (task 1.1)~~ | ~~ad-hoc REPL over 18 expressions~~ | — | **RETRACTED — recorded the P0 as correct.** It read "thứ 6 tuần sau"→2026-07-24 and "cuối tuần này"→07-18 (on a Saturday) as right. Both were wrong: 07-17 and 07-11. The REPL only re-derived the rule the code already implemented. Superseded by the invariant sweep below |
| Tool + registry (task 2.1) | `pytest tests/api/tools/test_date_tools.py tests/api/agent -q` | 0 | 99 passed; registry contract `tests/tools/test_tool_registry.py` 40/40 |
| `resolve_date` live invoke (task 2.1) | ad-hoc REPL | 0 | bound to planner/concierge/booking, readOnly; "khi nào rảnh thì đi"→ToolException telling the agent to ask. (Its "thứ 6 tuần sau"→2026-07-24 line carried the P0 and is retracted — the post-review tool returns 2026-07-17.) |
| Prompt booking v6 (task 3.1) | `pytest tests/api/agent tests/agents -q` | 0 | 214 passed; v5→v6 diff reviewed — booking-approval guardrails byte-identical |
| Grounding note (task 3.2) | `pytest tests/agents/test_state.py -q` | 0 | 14 passed |
| Tool error text (task 3.3) | `pytest tests/api/tools -q` | 0 | 14 passed; diff inspected — docstring/message lines only, no validation branch touched |
| Full suite (task 4.1) | `cd apps/api && mv .env .env.bak && DATABASE_URL=sqlite:///./full.db ../../.venv/bin/python -m pytest -q; mv .env.bak .env` | 0 | **1486 passed**. The repo `.env` must be set aside — it pins a real Postgres/OpenAI/ORS config that fails 5 unrelated tests regardless of this diff (known: `env-openai-key-test-breaks-llm-tests`) |
| Lint (task 4.1) | `cd apps/api && ruff check app scripts` | 0 | clean |
| ~~Live: weekday date (task 4.1, first attempt)~~ | ~~`POST /agent/chat {"message":"…thứ 6 tuần sau"}`~~ | — | **RETRACTED — this row recorded a WRONG answer as verified.** It read "24/07/2026" as correct for today = Sat 2026-07-11; the correct answer is **17/07**. Code review (P0) caught it. The check confirmed the code matched the pinned rule without ever checking the rule matched what "thứ 6 tuần sau" means. See the post-review rows below |
| **Live: weekday date → no question** (post-review) | `POST /agent/chat {"message":"tìm chuyến bay SGN đi HAN thứ 6 tuần sau"}` on a fresh thread, after `docker exec api-api-1 touch app/main.py` | 0 | Routed to **planner** (the dominant path, whose prompt the review found still ordered in-head math + a pre-search confirmation). Tool trace: `resolve_date` → `search_flights`. Reply: "chuyến bay SGN → HAN cho **thứ Sáu, 17/07/2026**" — correct date, stated in the traveller's language, no confirmation turn |
| **Invariant sweep** (post-review) | ad-hoc REPL: 14 consecutive anchor days × 3 weekdays | 0 | `resolve("<weekday> tuần sau")` always lands inside the 7-day window opened by `resolve("tuần sau")` — the P0 class is now closed by construction, not by one lucky anchor |
| **Live: no date → asks once** (post-review) | `POST /agent/chat {"message":"tìm chuyến bay SGN đi HAN"}` | 0 | No search tool called; one question ("bạn chưa nói **ngày bay**"), no default date. Still holds after the planner v7 rewrite |
| **Full suite + lint** (post-review) | `cd apps/api && mv .env .env.bak && DATABASE_URL=sqlite:///./f.db ../../.venv/bin/python -m pytest -q; mv .env.bak .env` · `ruff check app scripts` | 0 | **1526 passed** (was 1486 — +40 from the anchor sweep, invariant, overflow, past-date, punctuation and prompt-content tests added by the review) · ruff clean |
| **Phase 5 suite + lint** (LLM parser) | same commands | 0 | **1514 passed** · `ruff check app scripts` clean. Count drops from 1526 because the deleted lexicon took its per-word cases with it; the arithmetic invariants (7-anchor sweep, cross-form window) all survive, re-expressed over intents |
| **Phase 5 live: multilingual** | `POST /agent/chat` on fresh threads, after seeding the `date_resolution` model row + `docker exec api-api-1 touch app/main.py` | 0 | Every trace `resolve_date` → `search_flights`, no confirmation turn. "thứ 2 tuần tới" → **13/07** (the phrase the lexicon regressed on) · "thứ 6 tuần sau" → **17/07** (the P0 phrase) · "cuối tuần sau" → **18/07** · 来週の月曜日 → **13/07** · "el próximo viernes" → **17/07** · "the day after tomorrow" → **13/07**. None of the last three were expressible in the old lexicon |
| **Phase 5 live: no date** | `POST /agent/chat {"message":"tìm chuyến bay HAN DAD khi nào rảnh thì đi"}` | 0 | Model returns `kind="ambiguous"` → ToolException → the agent asks one question. No search tool called, no invented date |
| **Live: relative date → no question** (task 4.1) | `POST /agent/chat {"message":"tìm chuyến bay SGN đi HAN ngày mai"}` | 0 | Tool trace: `resolve_date` → `search_flights`. Reply states **12/07/2026** |
| **Live: no date → asks exactly once** (task 4.1) | `POST /agent/chat {"message":"tìm chuyến bay SGN đi HAN"}` | 0 | No search tool called. Reply: "bạn chưa nói **ngày bay** … Bạn muốn bay **ngày nào**?" — one question, no default date |

### Deploy note (phase 5)

`date_resolution` is a new agent-config node. `app/db/seed.py::_seed_agent_config` inserts the row
with **NULL provider/model**, and `get_agent_llm` then falls back to the env default
(`fast_llm_model = gpt-5-mini`, direct OpenAI) — which **403s** on this account, so every
`resolve_date` call failed with "hệ thống đang lỗi khi đổi ngày" until the row was given a model.
Any environment must seed it like its siblings:

```
docker exec -w /app -e PYTHONPATH=/app api-api-1 \
  python scripts/seed_agent_config.py --provider openai --model gpt-5.4-mini --nodes date_resolution
```

(Then rebuild the graph: `docker exec api-api-1 touch app/main.py`.) The failure is loud and
recoverable — the tool raises ToolException and the agent asks for a concrete date rather than
inventing one — but the feature is silently degraded until the row is seeded.

### Rollback

- Revert the whole feature (newest first, so the tree never passes through a broken state):
  `git revert --no-commit e6cd373 00a3e71 53637cf e833714 0e0a302 && git commit`
  (`e6cd373` = the post-code-review fix round; the four before it are the original waves.)
- Prompt-only rollback, no code revert needed: set `booking: 5` and `planner: 6` in
  `app/prompts/active.yaml` (versioned prompts — v5/v6 files are retained) and rebuild the graph
  with `docker exec api-api-1 touch app/main.py`. The `resolve_date` tool stays registered but the
  agent stops being told to use it, so behavior returns to ask-and-confirm.

### Harness-Delta

- backlog (→ `/compound`) — **Verifying an implementation against a rule I invented is not
  verification.** The P0 (`"thứ 6 tuần sau"` off by +7) survived a spot-check, 51 unit tests, and a
  live probe, because all three asked "does the code do what the pinned rule says?" and none asked
  "does the pinned rule say what the phrase means?" The tests pinned `today = Thursday` — the one
  anchor where the bug is invisible — and the SUMMARY then recorded the wrong answer as proof. Two
  cheap defenses generalize: parametrize over EVERY anchor when behavior depends on the anchor, and
  assert cross-form INVARIANTS (`"<weekday> tuần sau"` must fall inside the week `"tuần sau"` opens)
  rather than a table of expected values, since an invariant catches a wrong rule while a value table
  only re-states it.
- backlog (→ `/compound`) — **A negative grep is not evidence of absence.** I concluded "only
  `booking/v5` carries the confirm-date rule" from one filtered grep; `planner/v6` carried it too,
  wrapped onto a line the filter did not match, and planner is the *dominant* search path. The live
  probe passed anyway (the prepended grounding note happened to win over the contradictory prompt),
  so the feature looked delivered while the main path still ordered the old behavior. `behavior.md`
  already says `not_observed != absent`; the operational form is: when a prompt rule is being
  removed, enumerate every ACTIVE prompt and read it, never grep for the phrasing you remember.
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
