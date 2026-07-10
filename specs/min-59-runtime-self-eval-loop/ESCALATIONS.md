# Escalations — min-59-runtime-self-eval-loop

`ESCALATIONS.md` is deny-on-no-response: work listed here stays blocked until a human
records a decision.

---

## E1 — `grader` writing reflection's `revisions` counter disables reflection for the rest of the conversation

- **Status:** RESOLVED — human decision recorded 2026-07-10
- **Raised:** 2026-07-10, by `/correctness-review` (adversarial finder, score 75; independently
  confirmed by the controller with live-graph evidence, see below)
- **Severity:** P1 (wrong behavior on a common path — silent loss of self-correction)
- **Rule class:** Rule 4 — two materially different fixes with different blast radii; picking one
  is an architectural decision about shared state semantics, not an obvious auto-fix.

### What happens

`TravelAgentState.revisions` (`app/agents/state.py:30`) is a plain checkpointed field. It is
**never reset per turn**: `load_context_node` resets only `plan_approved`
(`app/agents/nodes.py`), and the router's per-turn graph input dict never seeds `revisions`
(`app/routers/agent.py`). The checkpointer therefore carries it across every turn of a thread.

`make_grader_node` increments that same counter (`app/agents/grader.py`), and
`make_reflection_node` reads it against `AgentContext.max_revisions`, which
`resolve_agent_context` hard-codes to `1`.

So: once a graded flow (booking/concierge) takes even **one** grader revision, `revisions >= 1`
persists. Any later turn in that thread routing to planner / journal / budget hits
`revisions(≥1) >= effective_max(1)` and **reflection short-circuits to END without ever calling
its judge** — permanently, for the rest of the conversation, with no error and no signal beyond
one INFO line.

### Why this diff makes it blocking (and what is pre-existing)

The *mechanism* (a turn-scoped counter that is never turn-scoped) is **pre-existing**: reflection
already self-locked out on turn 2 after revising on turn 1. It stayed latent because reflection
only revises when its judge emits `REVISE`.

This diff makes it **near-certain and cross-node**:

1. Live smoke on the dev stack (2026-07-10, `conversation_id=smoke-sse-1783677263`) shows the
   grader returning `needs_revision` on **every** concierge hotel turn, running the full budget
   to `max_iterations_reached` and leaving `revisions=2`.
2. A grader revision on `concierge` now disables reflection for `planner` / `journal` / `budget`
   — flows that never revised. Before this diff only reflection could write the field, so no
   cross-node contamination existed.

Reproduced end-to-end by the reviewer with two sequential `ainvoke` calls on one `thread_id` +
`MemorySaver`: turn 1 concierge grader-revises (`revisions=1`); turn 2 budget →
`node=reflection revisions=1` → `reflection → END (no revision)` with no judge call.

### Not covered by tests

`tests/agents/test_grader.py`, `tests/agents/test_depth_toggles.py` and the E2E tests in
`tests/api/agent/` all build single-turn state and never chain two invocations on one thread.

### Options (need a human to pick)

**Option A — give the grader its own counter.** Add `grader_iterations` to `TravelAgentState`;
grader reads/writes only that. Contained entirely inside the MIN-59 feature; removes the new
cross-node contamination; leaves the pre-existing reflection self-lockout exactly as it is today
(out of MIN-59 scope). Loses the "combined loop bound" the PLAN claimed — but that bound is
vacuous in practice: a graded flow never reaches reflection (the grader ends the turn), and when
the grader is disabled it never increments.

**Option B — reset `revisions` per turn** in `load_context_node`, alongside `plan_approved`.
Fixes the pre-existing latent bug too, so reflection starts actually revising on turn 2+ of a
thread. Touches a shared node used by every flow and changes reflection's real-world behavior
beyond MIN-59's stated scope — the PLAN lists "touching `make_reflection_node`" as a non-goal,
and this is adjacent to that.

**Option C — both** (A for containment now, B as a separate follow-up issue against reflection).

Controller's recommendation: **Option C**, shipping A on this branch and filing B separately, so
MIN-59 stays scoped and the pre-existing reflection bug gets its own change with its own test.

### Blocked work

Nothing else in the plan depends on this; Tasks 1–7 are complete and green. Task 8 (REPORT.md)
should not be measured until this is decided — the A/B latency/cost numbers would be taken
against a graph whose reflection arm is silently degrading over a conversation.

### Decision — Option C (human, 2026-07-10)

Shipped **A** on this branch: `TravelAgentState.grader_iterations` + `grader_verdict`, written only
by the grader; `revisions` is never touched. `load_context_node` resets both per turn, so a
turn-scoped budget is actually turn-scoped. **B** (reflection's own un-reset `revisions`) is a
pre-existing bug and gets its own issue + its own test — see "Follow-up" at the bottom of this file.

Verified live (dev stack, `thread_id=user_e4-u2_trip_none_conv_e4b-1783679904`):
`grader_iterations=2`, `grader_verdict='max_iterations_reached'`, `revisions=None` — the grader
never wrote reflection's counter. Regression test:
`tests/agents/test_grader.py::test_grader_never_touches_reflections_revisions_counter` and
`::test_grader_budget_does_not_leak_into_the_next_turn`.

---

## E2 — the grader ships enabled by default, but the intake says "gated off by default until measured"

- **Status:** RESOLVED — human decision recorded 2026-07-10
- **Raised:** 2026-07-10, by `/intent-review` (blind to PLAN; finding 1, most severe)
- **Severity:** P1 (unmeasured cost/latency on every booking + concierge turn in any environment)
- **Rule class:** Rule 4 — a runtime default with production cost blast radius.

`SUMMARY.md` → `### Rollback` states the user's own condition: *"prototype is additive; loop should
be gated off by default until measured."* The shipped code does the opposite:
`AgentContext.allow_grader` defaults `True` (`app/agents/context.py`), and `_resolve_context`
treats a NULL/absent `agent_config."grader".enabled` as on (`app/routers/agent.py`) — the
reflection-parity semantics the PLAN asked for.

Consequence: on deploy, with no dashboard action, **every** booking/concierge turn pays for the
judge call and any revise rounds. Live smoke (2026-07-10) measured that at **3 sub-agent
invocations + 2 judge calls** per concierge hotel turn vs. 1 + 1 on the baseline — i.e. the
unmeasured cost the intake explicitly said to avoid, incurred before REPORT.md exists to justify
it. (A non-hotel concierge turn — weather — was `satisfied` on the first grade: 1 judge call,
0 revisions. So the cost is topic-dependent, which is itself a reason to measure before enabling.)

**Options**

- **A — seed the `grader` row with `enabled = False`.** Keeps NULL-means-on semantics consistent
  with `reflection`; the dashboard checkbox turns the prototype on for measurement. Requires a
  seed/data change (`scripts/seed_agent_config.py` currently never writes `enabled`).
- **B — invert the default in code for grader only**: `AgentContext.allow_grader = False` and
  `_resolve_context` maps NULL → off. Contained, no data change, but `enabled=NULL` then means
  the opposite thing for `grader` than for `reflection` — a semantics trap for the next reader.
- **C — accept default-on**, and overrule the intake line, on the grounds that the toggle exists
  and the prototype wants real traffic. Requires an explicit human decision, recorded here.

Controller's recommendation: **A** — it honors the stated intent, keeps one meaning for NULL, and
makes enabling the prototype a deliberate, auditable act.

### Decision — Option A (human, 2026-07-10)

`app/data/agent_config.py` gained `SEED_DISABLED_AGENTS = {"grader"}`; `_seed_agent_config` sets
`enabled=False` **on insert only**, so re-seeding never clobbers an operator's toggle
(`tests/db/test_seed_agent_config.py::test_reseeding_never_clobbers_an_operator_toggle`).

> ⚠️ **The dashboard cannot toggle the grader today.** `app/templates/agent_config.html:378` gates
> the `enabled` checkbox on `d.agent === 'reflection'` — every other node's checkbox is hidden and
> disabled. So the only way to turn the grader on is a direct DB write:
> `update agent_config set enabled = true where agent_name = 'grader';`
> Widening that gate to `['reflection', 'grader']` is a one-line change, but the template currently
> carries another session's uncommitted work, so it is left as a follow-up rather than swept into
> this branch. Given the `HOLD` verdict in `REPORT.md`, nothing needs the toggle yet.

Verified live: after deleting the row and restarting, the seeded row is `grader|false`, and a
concierge turn logs `node=grader → reflection (delegated, flow=concierge)` — zero judge calls.

**Consequence for tests:** the grader is now off by default in any freshly-seeded DB, so the
API-level tests that script grader verdicts must force it on. A second `/correctness-review` pass
caught exactly this: `test_stream_emits_reset_on_revised_answer` passed only because the developer's
stale local `travel.db` still had `enabled=NULL`, and failed on a fresh DB (i.e. in CI). Fixed with
`_force_grader_enabled()`, called inside the `TestClient` block — the cache must be written *after*
lifespan wires its DB loader. Full suite now verified against a fresh SQLite file, not the stale one.

---

## E3 — the `failed` verdict does not exist, and no verdict is observable outside log lines

- **Status:** RESOLVED — human decision recorded 2026-07-10
- **Raised:** 2026-07-10, by `/intent-review` (finding 2)
- **Severity:** P2 (blocks the measurement deliverables, not the runtime path)
- **Rule class:** Rule 4 — the shape of the verdict output is a design decision.

The request names five verdicts: `satisfied` / `needs_revision` / `max_iterations_reached` /
`failed` / `grader_error`. In the code these exist only as free-text arguments to `logger.info`
in `app/agents/grader.py`. There is no `GraderVerdict` enum, no state field, nothing returned to
the router. `failed` (graded, still unsatisfied — as distinct from "ran out of budget") is not
representable at all.

Impact lands squarely on the deliverables: MIN-59 checklist items 5–7 ask for "% of requests that
trigger the loop", a grader false-positive/negative spot-check, and a trade-off report. With
verdicts confined to log text, the only data source for those numbers is grep over container
logs — which is how the controller had to gather the smoke evidence above.

Recommendation: add a `GraderVerdict` str-enum + persist the per-turn verdict (state field or a
structured log record) **before** Task 8, so REPORT.md is computed from data rather than grep.

### Decision — implement now (human, 2026-07-10)

`GraderVerdict` added to `app/enums.py`; every grader outcome writes
`TravelAgentState.grader_verdict` (the `.value` string, so the Postgres checkpointer serialises it).
Task 8 can now read verdicts off the checkpoint instead of grepping logs.

**`failed` was deliberately NOT added.** Once E4 makes the grader always grade the final draft,
`failed` ("graded, still unsatisfied, stopping") and `max_iterations_reached` ("the loop ran out of
rounds") describe the same event from two angles and cannot occur apart. Shipping both would mean
shipping one unreachable enum member with a docstring that lies. The enum documents this. If a
future change adds a second reason to stop (e.g. an unfixable-criterion signal from the judge),
`failed` becomes reachable and should be added then.

---

## E4 — the final revised answer is never graded

- **Status:** RESOLVED — human decision recorded 2026-07-10
- **Raised:** 2026-07-10, by `/intent-review` (finding 3); independently observed in live smoke
- **Severity:** P2 (the answer that reaches the traveller is the one nothing checked)
- **Rule class:** Rule 4 — fixing it costs one extra judge call per exhausted loop; a trade-off.

`app/agents/grader.py` checks `revisions >= max_iterations` **before** invoking the judge. With
`DEFAULT_MAX_GRADER_ITERATIONS = 2` the real sequence is:

    grade(draft1) → fail → draft2 → grade(draft2) → fail → draft3 → [cap hit] → END, draft3 unGRADED

So the answer actually returned to the traveller after a full revise loop is the one answer the
grader never looked at. The `max_iterations_reached` log line reads like a quality verdict; it is
not — it means "not graded". Live smoke confirms: every concierge hotel turn ended this way, and
the un-graded `draft3` was in fact the best of the three (it had dropped the hallucinated hotels).

The grader's own test encodes the behavior: `test_grader_stops_at_max_iterations` asserts
`llm._structured_cursor == 0`.

Options: (a) grade the final draft and emit `satisfied`/`failed` accordingly (+1 judge call on
exhausted loops only); (b) keep as-is and rename the log line so it cannot be misread as a
quality signal. Recommendation: (a) — it is what makes `failed` (E3) meaningful.

### Decision — Option (a) (human, 2026-07-10)

The cap is now checked **after** the judge call. A final revision that fixes everything ends
`satisfied`; one that does not ends `max_iterations_reached` — and in both cases the answer that
reaches the traveller has been graded. Costs one extra judge call only on loops that exhaust the
budget.

Verified live: the log line is now `grader → END (max_iterations_reached: grounding, completeness)`
— it names the failing criteria, which is only possible because the judge ran. Before the fix the
same line carried no criteria, because it never did. Tests:
`test_grader_grades_the_final_draft_before_stopping` (asserts the judge WAS invoked at the cap) and
`test_grader_satisfied_at_the_cap_still_ends_satisfied`.

---

## Follow-up (not blocking MIN-59)

**`reflection`'s `revisions` counter is never reset per turn.** Pre-existing, independent of MIN-59
now that the grader has its own counter. Effect: if reflection revises on turn 1 of a thread, then
`revisions=1 >= AgentContext.max_revisions=1` on every later turn, so reflection silently stops
judging for the rest of the conversation. Fix is one line in `load_context_node` (add `"revisions": 0`
to the reset dict) plus a cross-turn test. Needs its own change so the behavior shift — reflection
starting to actually revise on turn 2+ — is reviewed on its own merits.
