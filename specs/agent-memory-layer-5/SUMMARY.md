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
- **Day-precise fact age (`"3 days ago"`)** — rejected after research. It puts a daily-changing
  string mid-prefix in a prompt whose caching is on and measured at 71.9%, where the one volatile
  block was deliberately placed last. Month-granularity buckets keep that property and still
  answer the only question the model needs answered. The alternative that preserves day precision
  — moving the age-annotated blocks after `summary` — is a prefix-order change with a larger blast
  radius and does not belong in this spec. Owner confirmed month granularity 2026-09-16.
- **`llm.get_num_tokens_from_messages()` instead of a char/4 estimate** — rejected after research:
  `transformers` is not installed, so the base implementation raises for any model that does not
  override it, including the test `FakeLLM`.
- **Adding a `Tags.memory` member for the new routes** — rejected: `Tags` is a shared 19-member
  enum read by every router and its values are the generated OpenAPI tags. Mount under the
  existing `Tags.agent`; memory is agent state.

### Deviations

- none (no code changed)

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| plan contract | `python3 .claude/scripts/check_plan_contract.py specs/agent-memory-layer-5/PLAN.md` | 0 | run from repo root after the research-driven plan edits | |
| intake lane evidence | `python3 .claude/scripts/verify_summary.py --lane agent-memory-layer-5` | — | to run at handoff; SC coverage closes as tasks execute | |

### Not auto-verified

- **The `ON DELETE CASCADE` finding was read in source, never executed.** `research-brief.md`
  confirms `store_vectors` cascades from `store(prefix, key)` in langgraph 1.2.6, but no live
  database was touched — reached **provenance** (re-derived from the installed package, which is
  the source of truth for the running version), not **truth**. Task 1.1's Postgres test is the
  first actual execution; an absent `store_vectors` table means the store was created unindexed
  and delete semantics differ.
- **The prompt-cache regression is predicted, not measured.** The mechanism is documented and the
  71.9% baseline is real, but the specific cost of Task 2.1 was not measured. Task 4.1 records
  `cache_hit_report --since 24h` before and after; until it runs, the bucketing decision rests on
  inference.
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

### Harness-Delta

- backlog — `verify_summary.py --lane` fails at intake for any spec whose sibling `PLAN.md`
  declares an SC table, because SC coverage cannot exist before the tasks run (reproduced on
  `specs/memory-poisoning-hardening`, an already-shipped spec). The lane check and the SC-coverage
  check are two different gates sharing one exit code, so an intake-time run cannot distinguish
  "missing lane evidence" from "work not done yet". → `compound`.
