<!--
  Canonical SUMMARY.md shape. Copy to specs/<slug>/SUMMARY.md at intake.

  The header block is machine-read:
    - hooks/risk-corroboration.sh greps the `Lane:` line to corroborate it
      against the staged diff (a hard-gate signal in the diff + a Lane below
      high-risk = blocked).
    - the trust-metrics ledger reads Lane / Confidence / Flags per task.
  Keep the five header fields present and on their own lines. Do not delete them.
-->

# gh-106-reflection-toggle-not-honored — Summary

Lane: high-risk
Confidence: high
Reason: Human resolved E001 (decision B, 2026-07-21) — fix cross-process invalidation in `AgentConfigCache`. This trips the Rule-4 hard gate "replacing a service/pattern" (swapping/redesigning the shared cache's invalidation model), which forces high-risk regardless of flag count. Direction is no longer ambiguous, so confidence is high.
Flags: existing-behavior, weak-proof, replacing-a-service-pattern (hard gate)
Affects: app/core/agent_config_cache.py (AgentConfigCache — shared component), app/agents/context.py (AgentContext.allow_reflection), app/agents/nodes.py (make_reflection_node), app/routers/agent.py (_resolve_context)
Input-type: change request
Route: high-risk full chain — /brainstorming (genuine design fork: TTL reduction vs. Postgres LISTEN/NOTIFY vs. DB read-through vs. adding a shared cache like Redis) → /xia2 → /writing-plans → /using-git-worktrees → /subagent-driven-development

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- The user's request VERBATIM at intake — do NOT paraphrase or summarize. -->

GitHub issue #106 — "Reflection node still runs when disabled in DB config (enabled flag not fetched from DB)":

> ## Summary
>
> The reflection node still runs even when reflection is **disabled** in the DB agent config. The per-request "reflection enabled" flag does not appear to be fetched/honored from the DB, so turning reflection off in the dashboard config has no effect on the running agent.
>
> ## Expected
>
> Setting `agent_config.enabled = false` (or the equivalent reflection toggle) in the DB config should disable the reflection node for the request — the graph should skip reflection.
>
> ## Actual
>
> Reflection continues to run regardless of the DB config value. The disable toggle is effectively a no-op.
>
> ## Notes / where to look
>
> - Reflection toggle was shipped as: DB `agent_config.enabled` (nullable, `NULL` = on) → `AgentContext.allow_reflection` (per-request, no graph rebuild); dashboard modal checkbox.
> - Suspected causes to verify:
>   - The `enabled` value is not being read from the DB into `AgentContext.allow_reflection` at request time (config cache not populated / not reloaded).
>   - The reflection routing/conditional edge is not gating on `allow_reflection`.
>   - Prompt/graph baked at lifespan startup — config change not reflected without rebuild (config is meant to be per-request, so verify the per-request read path).
>
> ## Repro (to confirm)
>
> 1. In the dashboard agent-config, disable reflection for the agent.
> 2. Send a chat turn that would normally trigger reflection.
> 3. Observe reflection node still executes.

## What changed

Two bundled fixes, shipped via `specs/gh-106-reflection-toggle-not-honored/PLAN.md` (5 tasks / 4
waves, subagent-driven, in-session):

- **(A) `AgentConfigCache` cross-process freshness.** Replaced the pure-TTL refresh (unconditional
  full `reload_from_db()` every 1h) with a cheap DB version-poll: `AgentConfigRepository.max_updated_at()`
  (new — `SELECT MAX(updated_at)`, one scalar) is checked every `agent_config_poll_interval_seconds`
  (renamed from `agent_config_cache_ttl_seconds`, default lowered `3600` → `5`); the expensive full
  reload only runs when that value actually changed. No migration needed — `AgentConfig.updated_at`
  already exists (inherited via `UUIDBase`/`TimestampMixin`) and both write paths already bump it
  through the ORM. Both the poll+reload sequence is serialized under a `threading.Lock` (added after
  code-quality review found FastAPI runs this cache's caller via a sync dependency on a real
  threadpool thread per request, so concurrent `_maybe_refresh()` calls are the normal case) and the
  fail-open error handling is scoped to `sqlalchemy.exc.SQLAlchemyError` (narrowed from a bare
  `except Exception` after the final correctness review found the broad catch would silently mask a
  permanent/programming bug forever, not just a transient DB hiccup).
- **(B) Reflection-checkbox CSS fix.** The "Reflection enabled" checkbox visually rendered on every
  agent's dashboard-edit modal, not just `reflection` — root-caused to `.am-field { display: flex }`
  overriding the `hidden` HTML attribute's implicit `display: none` on `#am-enabled-field` (the JS
  already correctly gated `hidden`/`disabled` to `reflection` only; this was a pure CSS-cascade bug,
  visual-only, no data-integrity issue). Fixed with one ID-scoped rule:
  `#am-enabled-field[hidden] { display: none; }`.

### Rationale

An `Agent(Explore)` traced every hop end to end and found **no code-level bug**: `AgentContext.allow_reflection` is correctly resolved from `AgentConfigCache` in `_resolve_context()` (`app/routers/agent.py:197-224`), both `/chat` and `/stream` use that same helper, `AgentConfigCache.invalidate()` is correctly called on config update (`app/services/agent_config_service.py:121`), and `make_reflection_node` correctly gates on `runtime.context.allow_reflection` (`app/agents/nodes.py:181-188`). 42 existing tests pass, including a direct test of the DB→context resolution path (`tests/agents/test_agent_context.py::test_resolve_context_disables_reflection_from_db_config`).

The one gap found: `AgentConfigCache` is a **process-local, class-level singleton** with no cross-process invalidation. A dashboard save invalidates only the process that served that HTTP request; a multi-worker/multi-replica deployment would keep serving the stale `enabled=True` on sibling processes for up to `agent_config_cache_ttl_seconds` (1h default). This repo's own `docker-compose.yml` runs a single uvicorn process, so that specific mechanism would not reproduce here — meaning the reporter's repro conditions (worker count, environment) are unknown and materially change what "the fix" is.

This is why I escalated rather than picking one interpretation and implementing it — see
`### Alternatives considered`. The escalation (E001) was resolved by the user on 2026-07-21
(decision B — fix the architectural gap), which drove a full `/brainstorming` → `/xia2` →
`/writing-plans` cycle (`specs/gh-106-reflection-toggle-not-honored/{design.md,research-brief.md}`)
before implementation. That brainstorm ruled out Redis/pub-sub (new external dependency, no such
infra exists) and Postgres `LISTEN/NOTIFY` (engine-specific, breaks the SQLite-local/Postgres-Docker
duality, needs a new background asyncio task) in favor of the version-poll design shipped here — the
version marker it needs (`AgentConfig.updated_at`) turned out to already exist and already be
correctly maintained by both write paths, so no new schema was needed. A second, unrelated bug (the
CSS checkbox-visibility issue) surfaced during brainstorm verification against a running dashboard
and was folded into this same spec per user decision (`design.md` §2).

### Alternatives considered

At least three materially different resolutions exist, and picking one without reporter input risks solving the wrong problem:

- **A) Could-not-reproduce as filed.** Ask the reporter for deployment topology (worker/replica count) and exact repro steps (did they restart/wait past TTL? which process served the disable POST vs. the chat turn?). If single-process, the bug may not exist in this deployment and the issue may be a misunderstanding of the checkbox semantics or a stale `uvicorn --reload` process (a known adjacent gotcha, see memory `prompt-changes-need-graph-rebuild-not-hot-reloaded` — though that's documented for prompt files, not config, and `_resolve_context` reads per-request so it should not require rebuild).
- **B) Fix the real architectural gap.** If multi-worker/multi-replica is actually how this runs (locally or in prod), `AgentConfigCache`'s process-local invalidation is insufficient — would need either a shared invalidation signal (pub/sub, short TTL, or read-through-DB-per-request) — a design change to a shared component (`AgentConfigCache`), not a one-line fix.
- **C) Close the test gap regardless of A/B.** No test currently exercises the full path (dashboard POST → live `/agent/chat` graph run); add one so this class of regression is caught by CI even if this specific report turns out to be a non-repro.

None of these is a "small self-evident bug fix" — (A) needs reporter confirmation, (B) is a shared-cache architecture change (high-blast if adopted), (C) is worth doing regardless but doesn't address the reported symptom if (B) is real.

### Deviations

Every Rule 1–3 auto-fix applied during review loops (per-task spec/quality review, plus the final
adversarial correctness review):

- Rule 1 — Task 1.1 code-quality review: docstring overstated a general "ISO-8601 sorts correctly"
  claim; tightened to name the exact mechanism (isoformat's fractional-seconds omission at
  `microsecond==0` + ASCII ordering of `+`/`.`). `apps/api/app/repositories/agent_config.py`.
  Commit `804995d`.
- Rule 1 — Task 1.2 code-quality review: the new test's second assertion (`"display: none" in
  r.text`) was vacuous (two unrelated pre-existing rules in the same template already contain that
  substring); replaced with a regex checking the full rule (selector + declaration) together.
  `apps/api/tests/api/agent_config/test_agent_config_dashboard.py`. Commit `e18c790`.
- Rule 1 — Task 2.1 spec review: an adjacent comment in `lifespan.py` still said "wires the TTL"
  after the rename — stale terminology in the same commit's blast radius. `apps/api/app/core/lifespan.py`.
  Commit `a95d816`.
- Rule 1 — Task 2.2 code-quality review: `_maybe_refresh()`'s poll→conditional-reload→known-update
  sequence was not atomic across threads — FastAPI runs this cache's caller via a sync dependency
  (`GraphDep`) on a real threadpool thread per request, so concurrent calls are the normal case, not
  an edge case. Added a `threading.Lock` (`_refresh_lock`) serializing only the actual-refresh path
  (interval-check early-return stays lock-free). Also closed a test gap: the reload-failure test
  never asserted `_known_updated_at` stayed unchanged. `apps/api/app/core/agent_config_cache.py`,
  `apps/api/tests/core/test_agent_config_cache.py`. Commit `ec0550f`.
- Rule 1 — Final correctness review (score 100/100, certain): both `except Exception` blocks in
  `_maybe_refresh()` would silently swallow a permanent/programming error forever (not just a
  transient DB hiccup), contradicting the method's own "fails open on DB errors" contract. Narrowed
  to `except SQLAlchemyError`; updated the two fail-open tests to raise `SQLAlchemyError` instead of
  a bare `RuntimeError` so they still exercise the narrowed path. Independently re-verified the
  narrowing doesn't regress real DB-failure coverage (SQLite/Postgres connection/timeout/driver
  errors all surface as `SQLAlchemyError` subclasses through this code's query path).
  `apps/api/app/core/agent_config_cache.py`, `apps/api/tests/core/test_agent_config_cache.py`.
  Commit `3466447`.

### Verify

<!-- Evidence over assertion: one row per check that was actually RUN. -->

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Existing reflection-toggle test suite (intake) | `../../.venv/bin/python -m pytest tests/agents/test_agent_context.py tests/agents/test_depth_toggles.py tests/api/agent_config/test_agent_config_dashboard.py -q` | 0 | 42 passed — confirmed the pre-existing single-process paths worked before any code change. |
| Worktree baseline (pre-implementation) | `cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_agent_config_cache.py tests/api/agent_config tests/agents/test_agent_context.py tests/agents/test_depth_toggles.py -q` | 0 | 65 passed on branch `fix/gh-106-reflection-toggle-not-honored` before Task 1.1. |
| Full targeted suite (post-implementation, Task 3.1 + final) | `cd apps/api && ruff check app && ../../.venv/bin/python -m pytest tests/core/test_agent_config_cache.py tests/api/agent_config tests/agents/test_agent_context.py tests/agents/test_depth_toggles.py -x -q` | 0 | 72 passed, ruff clean — includes all new/rewritten tests from every task and review fix-loop. |
| Full repo suite (Task 2.2 self-check) | `../../.venv/bin/python -m pytest tests/` | 0 | 1758 passed; 9 pre-existing failures confirmed identical on the base commit (env/network-dependent, unrelated to this change) via `git stash` + rerun. |
| Final adversarial correctness review | 6-angle parallel FIND + independent SCORE (haiku) over `git diff cc56df5..ec0550f` | — | 4 deduplicated candidates; 1 scored ≥80 (100 — over-broad `except Exception`) and was fixed (commit `3466447`, independently re-verified); 3 scored <80, recorded below as Advisory Findings. |

### Rollback

- Revert code: `git revert <sha>` per task/fix commit (in reverse order, or as a range) — no
  migration, no schema change anywhere in this diff; every commit is additive/renamed code or a
  single CSS rule.
- Commits (oldest → newest): `835d26b`, `804995d`, `72a0ff9`, `e18c790`, `70c4dc5`, `a95d816`,
  `b0da5ab`, `ec0550f`, `3466447`.

### Advisory Findings

<!-- Below-threshold (score < 80) findings from the final adversarial correctness review.
     Not fixed, not discarded — reported for awareness. Nothing here blocks shipping. -->

- **`AgentConfigCache._maybe_refresh()`'s `MAX(updated_at)`-equality change-detection is an
  incomplete freshness signal** (`apps/api/app/core/agent_config_cache.py:134-141`, backed by
  `apps/api/app/repositories/agent_config.py:44-58`). Score: 50. Two named triggers: (1) a write
  whose `updated_at` doesn't exceed the current stored max (cross-process/cross-machine clock skew
  or an NTP backward step) is silently never detected as a change; (2) deleting a non-max-`updated_at`
  row doesn't change `MAX(updated_at)` at all, so a deleted override would keep being served. **(2)
  has no reachable trigger in current application code** — confirmed via `grep` for `delete`/`.delete(`
  across `app/services/agent_config_service.py`, `app/repositories/agent_config.py`,
  `app/routers/dashboard.py`, `app/db/seed.py`, `scripts/seed_agent_config.py`: only `upsert`/`add`
  exist, no delete path. (1) requires clock skew, which is a real but narrow condition. If a delete
  path or a genuine multi-machine deployment (not just multi-process) is added later, revisit this
  design — e.g. track `(COUNT(*), MAX(updated_at))` or a dedicated monotonic version column instead.
- **`invalidate()`'s immediate-refresh signal can theoretically be raced by a concurrent in-flight
  reload's `sync_from_cache()` re-stamping `_loaded_at`** (`apps/api/app/core/agent_config_cache.py`
  — `_maybe_refresh`, `sync_from_cache`, `invalidate`). Score: 75 (just below the 80 threshold).
  Under threadpool concurrency, a slow reload finishing after a concurrent `invalidate()` call could
  overwrite the `None` `invalidate()` just set, delaying (not losing) the config's visibility by up
  to one `poll_interval_seconds` (5s default) instead of taking effect immediately. Self-heals on
  the next poll; does not affect eventual correctness, only latency of the same-process fast-path.
  Worth closing in a follow-up if the instant-refresh guarantee needs to be airtight (e.g. have
  `invalidate()` acquire `_refresh_lock`, or have `sync_from_cache` only stamp `_loaded_at` if it
  wasn't concurrently cleared).
- **`MAX()` ordering on the `updated_at` `String` column assumes ASCII/binary collation**
  (`apps/api/app/repositories/agent_config.py:44-58`). Score: 25. This repo's actual Postgres image
  (`pgvector/pgvector:pg17`, `docker-compose.yml`) defaults to `C` locale with no explicit
  `LC_COLLATE` override, so the assumption holds for the deployment this repo actually ships — the
  risk is theoretical unless a future deployment explicitly configures a non-`C` Postgres collation.

### Intent Findings

<!-- From the final intent-review pass (blind to PLAN.md, oracle = ### Intent above + design.md
     Success Criteria). gap/drift-different route to fix-loop or escalation; drift-equivalent and
     excess are report-only. -->

- **excess (report-only)** — the `threading.Lock` (`_refresh_lock`) added to
  `AgentConfigCache._maybe_refresh()` (`apps/api/app/core/agent_config_cache.py`) is not traceable
  to the verbatim intent or to `design.md` (neither mentions locks or threads — the design's
  concern was cross-*process* freshness, not intra-process thread races). Confirmed correct and
  kept, not removed: the lock is not scope creep — it's the fix for a concrete correctness finding
  from the final adversarial correctness review (Task 2.2 code-quality review, independently
  re-verified twice): FastAPI runs this cache's caller (`GraphDep`) via a sync dependency on a real
  threadpool thread per request, so the poll→conditional-reload→known-update sequence genuinely
  races across concurrent requests without serialization — without the lock, the cache could get
  stuck serving stale config under load, which would directly undermine the intent's own goal
  ("becomes visible to every process within seconds"). Removing it would reintroduce that race.
  Recorded here per the intent-review residual gate rather than auto-removed (Rule-4: removing
  shipped functionality needs human approval) — no removal is being proposed; this entry is the
  record.

### Harness-Delta

- backlog — Explore-agent investigations that conclude "no bug, but a coverage/architecture gap"
  don't have a clean home in the lane table (it's not tiny/normal/high-risk work yet, it's a
  decision that needs a human). Consider documenting this "investigate-before-lane" pattern in
  `feature-intake/SKILL.md` for bug reports that turn out to need reporter clarification before
  intake can even assign confidence.
- backlog — `hooks/blast-radius-check.sh` produced a false-positive "file not in the active plan's
  `<files>` set" warning on **every single task** in this execution, even when the file was listed
  verbatim under that task's markdown `- **Files:**` bullet in `PLAN.md`. This plan used the current
  (post-2026-07-16) markdown task format exclusively, with no legacy XML `<files>` tags — the hook
  appears to only parse the legacy XML shape. Every subagent correctly treated this as a known false
  positive and proceeded (per their own verification against the plan text), but the hook itself
  should be updated to also parse markdown `- **Files:**` bullets, or this will misfire on every
  markdown-format plan going forward.
