# agent-memory-layer-5 — Summary

Lane: high-risk
Confidence: high
Reason: two block-mode hard gates fire — `audit/security` (traveller memory is persistent data re-injected into every system prompt; this adds the delete path for it) and `public-contract` (new `/memory` REST routes + response envelope). 5 flags total.
Flags: audit/security, public-contract, existing-behavior, multi-domain, weak-proof
Affects: apps/api/app/memory/store.py, apps/api/app/agents/{nodes,state}.py, apps/api/app/routers/ (new `memory.py`), apps/api/app/core/config.py, apps/web/src/app/ (new settings surface), apps/web/src/lib/api/schema.d.ts
Input-type: new spec
Route: brainstorming (design.md — done) → xia2 Deep (research-brief.md — done) → writing-plans (PLAN.md — drafted) → using-git-worktrees → subagent-driven-development
Escalate: resolved — hard gate narrowed by the owner on 2026-09-16 (three scope questions; see `### Hard-gate narrowing`). One in-flight escalation raised and decided the same day: `ESCALATIONS.md` E001 → **decision A** (ship the #214-independent subset; defer P0#3).

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> `/Users/minhtran/Downloads/Agent\ Memory\ —\ The\ 5-Layer\ Playbook.pdf`
> review the playbook above and review ccurrent project archirtecture. let me know what part we should and can apply? explain why and how.
> make sure understand to define correct appoarch for current project because we need to launch to production

Follow-up (scope-deciding):

> viết specs/agent-memory-layer-5 cho 4 việc P0

> viết nốt research-brief.md rồi run xia2 luon

The four P0 items, as stated in the review that this spec instantiates:

1. Ship PR #214 (memory guard: key allowlist + length cap + deterministic blocklist + untrusted-data delimiter).
2. Render the age of each stored fact into the system prompt, so `state.py`'s existing
   "confirm before acting on stale ones" instruction stops being a no-op.
3. Endpoint + UI for a traveller to view and delete their own memory.
4. Context budget by token, not by message count.

### Hard-gate narrowing

The `audit/security` + `public-contract` gates were narrowed by the owner at intake
(2026-09-16), with these three decisions recorded as binding scope:

| Question | Decision | Consequence for this spec |
| --- | --- | --- |
| Which memory kinds does the management surface cover? | **All three** (`prefs`, `procedural`, `episodes`) | `procedural` is included specifically because standing instructions are what gets injected into every system prompt — a guard that blocks *new* poison cannot remove poison already in the store. |
| Delete semantics? | **Hard delete** (`store.delete`) | No tombstone/soft-delete; this is a privacy path, and `BaseStore` has no soft-delete concept, so a bolt-on would force a filter into every read site. |
| Relationship to PR #214? | **Dependency, not merged into this spec** | P0#1 stays in #214. This spec carries only P0#2/#3/#4, plus a gate task asserting the guard is present at the base commit before the `/memory` write path ships. |

A fourth decision was taken after research (2026-09-16): **fact age renders as a
month-granularity bucket**, not a day count — see `### Alternatives considered`.

### Scope

**In scope for this delivery** — P0#2 (fact age in prompt) and P0#4 (token budget), plus the
store-layer `list_memory` / `delete_memory` helpers, which ship **unreachable**: no HTTP route, no
agent tool and no UI calls them, and `PLAN.md` Task 0.1 pins that with a test asserting the OpenAPI
document has no `/memory` path.

**Deferred, blocked on PR #214** — P0#3 (the `/memory` routes, generated client types and settings
UI). PR #214 is OPEN with all four CI jobs failing; per `ESCALATIONS.md` E001 the owner chose to
ship the independent subset rather than either wait or invert the intended order. The full task
specs are preserved, fenced, in `PLAN.md` §6 along with the procedure to unblock them.

**Out of scope entirely** — P0#1 itself (PR #214). Also deliberately excluded, per the review's
"dứt khoát không áp dụng" list: knowledge-graph/ontology traversal, procedural skill
promotion + skill versioning, Mem0/Zep migration, hierarchical summarization, hot/warm/cold
tiering. See `design.md` §6.

### What changed

Nothing in the product yet — intake, design, research brief and plan only. No code has been
touched. Research produced three corrections to the plan before any code was written; they are
recorded in `PLAN.md` → Status Log and in `### Alternatives considered` below.

### Rationale

The playbook's Layer 5 (forgetting) is entirely absent from this codebase
(`grep -rni "ttl\|expire\|forget\|supersede\|prune\|retention\|archive" apps/api/app`
returns zero hits under `app/memory/`), and there is no route by which a traveller can
inspect or remove what the agent has stored about them
(`grep -rn "memor" apps/api/app/routers/*.py` matches only the extraction-runner import in
`agent.py`). Both are launch blockers: the first makes a stale fact indistinguishable from
a fresh one, the second is a privacy gap on data that includes inferred `gender` and
`travel_group`. Each is fixable without new infrastructure, a new dependency, or a schema
migration — which is why they are P0 and the rest of the playbook is not.

### Alternatives considered

- **Full Layer-5 forgetting engine (scheduled cron: expire + supersede + contradiction
  detection)** — rejected for P0. It is the playbook's own recommendation, but it needs a
  scheduler, a retention policy per kind, and a conflict model this codebase has no data to
  calibrate yet. The two cheap halves (render age; let the owner delete) deliver most of the
  behavior with none of the infrastructure. Deferred to P1, tracked in `design.md` §6 — where
  research then changed the *implementation* from "build a read filter" to "use langgraph's
  built-in `TTLConfig`", since the capability is already installed.
- **Adopt the playbook's TTL numbers verbatim (30/90 days)** — rejected. Those are written
  for a coding agent. Travel preferences are seasonal and annual; a 30-day episode TTL would
  delete exactly the memory that becomes useful one year later.
- **Soft delete with a `status` field** — rejected at intake by the owner (see narrowing table).
  Research removed its last technical argument: hard delete leaves no orphaned embedding row,
  because `store_vectors` cascades.
- **Token budget replaces the message-count threshold** — rejected in favour of an OR. Replacing
  it removes existing behavior (a `remove-functionality` judgment gate) for no gain; an OR is
  strictly more conservative and keeps every current `should_summarize` test valid.
- **Day-precise fact age (`"3 days ago"`)** — rejected: it changes daily in a cached prompt and
  buys nothing the model needs. **But the reasoning first recorded here was wrong**, and the owner's
  initial approval rested on it. It claimed "the preferences and instructions blocks sit before
  `summary`"; in fact `state.py` appends `preferences` **last**, with only the already-daily date
  note after it. The cache argument therefore holds for `instructions` (position 3) and is largely
  false for `preferences` (position 8). Both reviews caught this independently; the decision was
  re-put to the owner with the ordering corrected, and they chose the **split**: coarse for
  `instructions`, finer for `preferences`. Corrected 2026-09-16 here and in `research-brief.md`,
  `design.md` §4.1, PLAN Global Constraints, and the `format_age` docstring.
- **`llm.get_num_tokens_from_messages()` instead of a char/4 estimate** — rejected after research:
  `transformers` is not installed, so the base implementation raises for any model that does not
  override it, including the test `FakeLLM`.
- **Adding a `Tags.memory` member for the new routes** — rejected: `Tags` is a shared 19-member
  enum read by every router and its values are the generated OpenAPI tags. Mount under the
  existing `Tags.agent`; memory is agent state.

### Deviations

- **Rule 1 — `list_memory` key precedence.** Rows were built as
  `{"key": item.key, **item.value}`, letting a stored value shadow the store key that is the
  delete handle. Reordered. Commit `918cbf84`.
- **Constraint exceeded — the preferences prompt clause was REPLACED, not appended to.** PLAN's
  Global Constraints said "additive prompt changes only … may append a parenthetical and one
  clause". The correctness/intent reviews (M1/D-2) then showed the appended wording
  ("anything recorded **more than a few months ago**") *loosened* the rule against the emitted
  vocabulary — `format_age` emits the literal phrase "a few months ago" for the whole 1–11 month
  span, so an 11-month-old preference was told **not** to be confirmed, weaker than the
  unqualified base text it replaced. Extending the clause could not fix that; it had to be
  rewritten to key off the one fresh marker. The constraint in PLAN is amended with the same
  note. **This entry exists because a reviewer found the record saying `none` while the block had
  been rewritten — not because the deviation was self-reported.**
- **Scope creep, reverted.** `ruff format app tests/memory tests/agents` was run over whole
  directories instead of the changed files, reformatting 8 unrelated files (`app/agents/metrics.py`,
  `app/repositories/agent_run.py`, `app/schemas/tip.py`, `tests/agents/test_graph.py`,
  `test_pii_redaction.py`, `test_state.py`, `test_supervisor.py`,
  `tests/memory/test_structured_namespaces.py`). All 8 restored with `git checkout --`; the diff
  carries only the 6 intended files. Notably `test_structured_namespaces.py` is the file the Task
  1.1 subagent had deliberately left alone as out-of-scope (it carries pre-existing ruff errors) —
  the controller was less disciplined than the subagent there.
- **Post-review fixes** (all with a regression test; see `### Verify`): H1/D-3 no-progress
  compression loop, H2 summary replacement, M1/D-2 staleness rule, D-1 granularity split,
  M2 false "this month" label, M3 future timestamps.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| plan contract | `python3 .claude/scripts/check_plan_contract.py specs/agent-memory-layer-5/PLAN.md` | 0 | run from repo root after the research-driven plan edits | |
| P0#3 deferral pinned (no `/memory` route, no router reference) | `.venv/bin/python -m pytest apps/api/tests/api/routes/test_no_memory_route_yet.py -q` | 0 | 2 passed | SC-1 |
| store carries `updated_at`; `format_age` buckets, `None` on absent | `.venv/bin/python -m pytest apps/api/tests/memory/test_fact_age.py -q` | 0 | 15 passed | SC-2 |
| prompt renders month-coarse age, omits it when absent, never a day count | `.venv/bin/python -m pytest apps/api/tests/agents/test_memory_age_prompt.py -q` | 0 | 7 passed; sweeps a year of offsets for day-count vocabulary | SC-3 |
| token-pressure OR branch fires; message-count branch still fires | `.venv/bin/python -m pytest apps/api/tests/memory/test_summarize_token_budget.py -q` | 0 | 5 passed; existing summarizer tests unmodified | SC-4 |
| `delete_memory` removes row + pgvector embedding (cascade pin) | `.venv/bin/python -m pytest apps/api/tests/memory/test_memory_delete.py -q` | 0 | 6 passed on `InMemoryStore`; the Postgres case skips under sqlite — it was separately RUN against live Postgres (see note below) | SC-5 |
| cascade confirmed by execution on live Postgres | `.venv/bin/python -m pytest apps/api/tests/memory/test_memory_delete.py -q -k postgres` (with `DATABASE_URL` = dev Postgres) | 0 | 1 passed. Independently probed: row counts in `store` / `store_vectors` go 1/1 → 0/0 after `delete_memory` | SC-5 |
| full backend suite | `.venv/bin/python -m pytest -q` (from `apps/api/`, sqlite) | 0 | 2642 passed, 7 skipped, 241s | |
| lint | `ruff check app scripts` (from `apps/api/`) | 0 | All checks passed; `ruff format --check` clean on changed files | |
| prompt-cache BEFORE reading | `.venv/bin/python -m scripts.cache_hit_report --since 7d` (from `apps/api/`, dev Postgres) | 0 | overall 80.3% — assistant 81.9%, supervisor 75.1%, reflection/synthesize 0% (sub-floor prompts, always 0%) | SC-6 |
| agent behaviour: eval smoke, this branch | `.venv/bin/python -m eval --suite smoke --out eval/reports/latest.json` (from `apps/api/`) | 0 | 18 cases, real agent. memory 2/2; budget/errors/flight_search/journal/language/routing 2/2 each; dates 3/4 ok; **hotels 1/2 BELOW THRESHOLD**. The runner exits 0 anyway — the threshold line is the gate, not `$?` | SC-6 |
| the two failures are pre-existing, not a regression | `.venv/bin/python -m eval --suite smoke --capability hotels` and `--capability dates`, run in a throwaway worktree at base `da546c92` | 0 | Same two cases fail with byte-identical details: `hotels-happy-en-01` → `tools_expected` `expected=['browse_hotels'] called=['needs_clarification']`; `dates-ambiguous-en-02` → `no_invented_date` `search_flights.departure_date='2026-09-16'` | SC-6 |
| H1/D-3: token branch makes no empty promise; no paid call on a no-op compression | `.venv/bin/python -m pytest apps/api/tests/memory/test_summarize_token_budget.py -q` | 0 | 9 passed. Probed directly: 3 heavy msgs → `should_summarize` False (was True), `summarize_conversation` → `("", [])` with an LLM that raises if called; 6 heavy msgs still True | SC-4 |
| H2: a repeated compression merges the rolling summary instead of replacing it | `.venv/bin/python -m pytest apps/api/tests/memory/test_summarize_token_budget.py -q -k merges` | 0 | asserts the prior summary reaches the model and the merge prompt carries its 250-word growth cap | SC-4 |
| M1/D-2 + D-1: staleness rule keys off the one fresh marker; preferences fine / instructions coarse | `.venv/bin/python -m pytest apps/api/tests/agents/test_memory_age_prompt.py -q` | 0 | 8 passed; 200-day row renders `about 6 months ago` in preferences and `a few months ago` in instructions | SC-3 |
| M2/M3: freshest label makes no calendar claim; a future stamp renders no marker | `.venv/bin/python -m pytest apps/api/tests/memory/test_fact_age.py -q` | 0 | 17 passed; `"this month"` absent from both vocabularies; future stamp → `None` | SC-2 |
| post-fix regression sweep | `.venv/bin/python -m pytest apps/api/tests/memory apps/api/tests/agents -q` | 0 | 560 passed, 1 skipped (the Postgres cascade pin, under sqlite) | |
| lint after the fixes | `ruff check app scripts` + `ruff format --check` on the 6 changed files (from `apps/api/`) | 0 | All checks passed; 6 files already formatted | |
| intake lane evidence | `python3 .claude/scripts/verify_summary.py --lane agent-memory-layer-5` | 0 | passes | |

### Not auto-verified

- **The prompt-cache AFTER reading does not exist.** The BEFORE reading is recorded above
  (80.3% over 7d). `eval-smoke` **cannot** supply the AFTER reading: `eval/adapters/langgraph_runner.py`
  invokes the graph directly and never passes through the `/agent/*` router, which is what writes the
  `agent_runs` / `agent_run_step` rows `cache_hit_report` reads. An AFTER reading needs real turns
  through the API. Until then the month-bucket decision rests on **inference** from the documented
  mechanism, not measurement — this is the open half of `SC-6`.
- **`make eval-check` (judged, paid) was not run.** Only `eval-smoke` was authorized. No claim is
  made here about judged metrics or about the `eval/baselines/main.json` regression gate.
- **The recorded `eval-smoke` result predates the post-review fixes.** It was run against the diff
  as it stood at `49bd91df`. H1 changed the compression trigger, H2 changed the summarizer prompt,
  and D-1/M1/M2 changed the preferences prompt — so that run describes a diff that no longer
  exists and must be repeated before the eval evidence can be claimed for the shipped code.
- **The correctness review's LOW findings (L1 onward) were never received.** Both review reports
  truncated mid-sentence in delivery and only the HIGH/MEDIUM items were recovered. The disposition
  table above is therefore complete for HIGH/MEDIUM and *incomplete below that*.
- **The two eval failures were attributed by re-running the same goldens at base, not by reading the
  baseline file.** `eval/baselines/main.json` is the `full` suite and excludes all 18 smoke goldens,
  so it contains `hotels-happy-en-02` but not `hotels-happy-en-01` — it could not have settled the
  question either way.
- **langgraph's Postgres read paths were not checked for expired-row filtering.** Upstream
  langgraph#5178 / #8905 report `omit_expired` being ignored in *sqlite* store reads. Irrelevant
  to this P0 slice (no TTL is set here) but load-bearing for the P1 TTL item in `design.md` §6.
- **PR #214's guard is assumed present at the base commit.** Reached traceability only
  (memory note + `SUMMARY.md` of `specs/memory-poisoning-hardening`); not re-run. Task 0.1
  turns this into a real check.
- **The eval gap stays open.** No golden asserts "an injected instruction is NOT stored"
  (`eval/datasets/memory.json` runs `flow_match` / `tools_expected` / `reply_language` /
  `memory_recall` across 12 cases; none is a poisoning case). PR #214 deferred it as its
  Task 4.1 and the owner kept it there — it is *not* picked up by this spec. Per
  `docs/solutions/agent/eval-golden-notes-are-not-metrics.md`, a golden whose `notes` describe
  the behavior but whose `metrics` do not check it is not a gate.
- **Store age data on pre-existing rows.** `_stamped()` has been writing `updated_at` since
  D5 store hygiene, but no check confirms every live row carries it; Task 1.1 must render
  no age suffix rather than guess when the field is absent.

### Rollback

- P0#2 / P0#4 — `git revert <sha>`; both are additive and behind existing code paths.
- P0#3 — `git revert <sha>` removes the routes. **Deletes already performed through the API
  are not recoverable** (hard delete, by design). This is the one irreversible surface in the
  spec; it is why `DELETE /memory` (delete-all) requires an explicit confirmation token in the
  request rather than being a bare verb — see `design.md` §4.3.

### Review findings and disposition

Correctness and intent review both ran at base `da546c92` (`reviewer` agent type: read-only by
construction, distinct model class). They converged independently on the two most serious items,
which is why those were treated as confirmed rather than argued with.

| ID | Finding | Disposition |
| --- | --- | --- |
| H1 / D-3 | Token branch fires forever while compressing zero messages — a paid summarizer call per turn with no context relief. A regression the OR branch introduced. | **Fixed** + 2 tests |
| H2 | `summary` replaced rather than merged; repeated firing narrows it to the last window while the messages behind it are already deleted → in-session amnesia | **Fixed** (owner authorized widening scope: the behaviour predates this change) + test |
| M1 / D-2 | "more than a few months ago" self-excludes the 1–11 month bucket it was meant to catch; *looser* than the base text | **Fixed** + test |
| D-1 | The cache rationale was false for `preferences` (it is last, not before `summary`) | **Fixed** in code (granularity split, owner re-approved) and corrected in 5 documents |
| M2 | `"this month"` asserted a calendar fact the code does not compute | **Fixed** + test |
| M3 | Future timestamps rendered as the *freshest* possible label | **Fixed** (→ `None`) + test |
| M6 | This SUMMARY said `Deviations: none` while the prompt block had been rewritten past a plan constraint | **Fixed** — see `### Deviations` |
| M4, M4b, M5 | Latent defects in the deferred `list_memory` / `delete_memory` (dishonest delete result, unmapped `ValueError`, silent 50-row truncation) | **Pinned in `PLAN.md` §6** as must-fix-on-unfencing; unreachable today (no route) |
| L1+ | Remaining low-severity items | Not yet dispositioned — the review report was truncated; see `### Not auto-verified` |
| Profile block | `name`/`gender`/`travel_group` carry no age marker (`get_profile` drops `updated_at`) | Accepted narrowing; noted for follow-up |

### Harness-Delta

- backlog — **`ruff-on-edit` strips an import added before its first use.** Adding the `format_age`
  import in one edit and its call site in the next left `nodes.py` with a `NameError`, which the
  best-effort `except Exception` in `load_context` then swallowed into a log line: the turn
  continued with **no preferences at all**. `docs/solutions/.../ruff-on-edit-strips-unused-imports`
  already records the hook behaviour; what is new is the failure *mode* — a programming error in a
  best-effort block silently disables personalization rather than failing. Candidate P1: let
  `NameError` / `AttributeError` propagate there while still swallowing store I/O errors. → `compound`.
- backlog — **`--suite smoke` exits 0 with a capability under threshold.** `python -m eval` printed
  `hotels ... BELOW THRESHOLD` and still exited 0, so any gate wired to the exit code reads a
  failing capability as a pass. → `compound`.
- backlog — **the blast-radius hook bound to the wrong spec for this entire session.** It warned
  against `specs/gh-193-booking-revise-idempotency/PLAN.md` on every edit, because this plan is
  `status: proposed` and the hook picks the first `status: active` plan alphabetically. Flipping the
  status would not have helped: harness scripts running inside a worktree read the *main* checkout's
  `specs/`, where this plan does not exist. Every warning this session was a false positive. → `compound`.
- backlog — `verify_summary.py --lane` fails at intake for any spec whose sibling `PLAN.md`
  declares an SC table, because SC coverage cannot exist before the tasks run (reproduced on
  `specs/memory-poisoning-hardening`, an already-shipped spec). The lane check and the SC-coverage
  check are two different gates sharing one exit code, so an intake-time run cannot distinguish
  "missing lane evidence" from "work not done yet". → `compound`.
