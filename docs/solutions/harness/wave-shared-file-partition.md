---
problem_type: failure
module: harness
tags: subagent-parallelism, wave-parallelism, blast-radius, test-infra, shared-types
severity: critical
applicable_when: Dispatching ≥2 parallel wave subagents that will consume shared test infrastructure or a shared type contract.
affects:
  - apps/web/src/test/setup.ts
  - apps/web/src/lib/api/keys.ts
supersedes: null
confidence: high
confirmed_at: 2026-06-26
---
## Applicable When

Watch for this when dispatching two or more parallel wave subagents whose tasks each legitimately edit their own files but all **import a shared module** — a test harness, a shared type/contract, or a shared config.

## Symptom

A parallel wave (3 concurrent subagents) passed the wave-parallelism guard (disjoint declared `<files>`), but the agents collided on files **no task declared**: `apps/web/src/test/setup.ts` (the shared MSW/openapi-fetch test harness, which every test task needed but no task owned) and a cross-file `qk` query-key param **type** (a `Record` index-signature spanning `lib/query/trips.ts` + `places.ts`). The collisions were reconciled only by manual diligence — one agent left a fix uncommitted for another to pick up — not by isolation.

## Wrong Approach

Relied on the wave-parallelism Invariant 1 / `hooks/blast-radius-check.sh` declared-`<files>` overlap check as sufficient proof of parallel-safety, and dispatched the wave without first establishing the shared test harness or shared type contracts.

## Why It Failed

The overlap guard only diffs each task's **declared** `<files>`. It is blind to:
- **Shared infrastructure** a task must touch but didn't declare (the test harness none of them "owned").
- **Shared type contracts** — a single type signature edited from multiple files each task legitimately owns is a shared *mutable surface* even with zero declared-path overlap.

Parallel-safety must be checked at the dependency/import level, not just the declared-path level.

## Correct Approach

Create/own shared test infrastructure and shared type contracts in an **earlier, single-task (non-parallel) wave**, before any parallel wave consumes them — and explicitly instruct parallel agents NOT to touch shared files. (This session ended up creating the harness retroactively in Wave 1 once the lesson landed; later waves that pre-owned shared keys/types ran with zero friction.)

## Guardrail

proposed: extend `hooks/blast-radius-check.sh` to compare each wave subagent's **actually-touched** files (from its git diff) against its task `<files>` and flag any file edited outside the declared set — backing the "blast radius beyond plan" in-flight escalation already in `rules/orchestration.md`. Complementary planning-time lint: require any file/type-module imported by ≥2 same-wave tasks to be produced in a prior non-parallel wave. Target path: `.claude/hooks/blast-radius-check.sh`.

## Related
- docs/solutions/monorepo/operate-from-subdir.md
- docs/solutions/harness/commit-gate-bare-python.md
