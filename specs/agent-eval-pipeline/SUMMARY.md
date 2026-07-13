# agent-eval-pipeline — Summary

Lane: normal
Confidence: medium
Reason: Extends the existing offline eval harness (flags: existing behavior, weak proof around eval coverage); no hard gates — offline tooling, no public API contract, no auth/data-model change.
Flags: existing behavior, weak proof
Affects: apps/api/eval/ (offline eval harness), apps/api/.deepeval
Input-type: new initiative

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- verbatim -->

> review current code changes and research evaluation pipeline for current project.
> I want to build the standard pipeline to evaluate the chatbot agent. Building the matrix, metrics, scripts, etc ...
> Help to ez mantain and scalable for testing/evaluation system when go to production

## What changed

Plan phase complete: `research-brief.md` (repo deep-dive + uncommitted-changes review + external best practices) and `PLAN.md` (9 tasks / 4 waves). One hygiene edit: `.deepeval/` added to root `.gitignore` (runtime cache/telemetry, regenerated per run). No agent/app code changed.

### Rationale

Two user-accepted constraints drive the shape: (1) **portability** — the engine (`evalkit/`) is built framework-free with `typing.Protocol` ports from the first commit and an ast boundary test forbidding `app.*` imports, so extraction into a standalone package / MCP server later needs no rewrite; (2) **DB-as-Oracle** — because this backend is deterministic (MD5-seeded flights/hotels, DB-backed trips/FX), eval recomputes ground truth from the DB instead of asking a judge, wherever a fact is computable. Judged G-Eval (temp-0, k-repeats, per-capability binary pass rates) covers only subjective qualities and runs nightly; the PR gate is keyless/deterministic.

### Alternatives considered

- **Build inside `eval/` and "extract later"** — rejected: the extraction step never happens; the port boundary is cheaper to hold from day one than to retrofit.
- **Build the MCP server now** — rejected: nothing stable to expose until the Report JSON contract exists; MCP is a transport shell over the ports (phase 3).
- Confident AI cloud for baselines/regression — rejected: local-first, self-maintained.
- LangSmith for tracing — rejected: self-host requires Enterprise; Langfuse (MIT) is the phase-2 candidate.
- Judged eval on every PR — rejected: judge cost + variance.

### Deviations

- Rule 2 — Added `.deepeval/` to root `.gitignore` (generated cache/telemetry was untracked noise). Blast-radius hook flagged it against the stale active plan `specs/web-trip-planner/PLAN.md`; it belongs to this slug's scope.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| (pending — plan phase) | — | — | — |

### Rollback

- `git revert <sha>` (per-wave commits once implementation starts)

### Harness-Delta

- none
