---
slug: agent-memory-layers
created: 2026-06-30
---

# SUMMARY — agent-memory-layers (P1)

- **Lane:** normal
- **Confidence:** high
- **Reason:** Multi-file, multi-layer agent change (store + state + context + nodes
  + graph + prompt) → needs a plan. No hard gate: no auth/authz, no DB migration
  (store table already exists), no external provider, no public API contract change
  (internal agent behavior only), no high-blast file. Foundation (`BaseStore`,
  `system_with_summary`, `Runtime.store`) is well understood → high confidence.

## Status

Plan-only so far. Artifacts written: `research.md`, `design.md`, `PLAN.md`.
Execution not started — awaiting review of the plan before any code edit.

## Rationale

Apply the applicable parts of LangChain's memory framework (procedural memory +
background writes) using existing LangGraph primitives; skip the LangSmith SaaS
loop, which conflicts with the repo's provider-agnostic design. P2 (episodic) is
deferred.

## Alternatives considered

- Async fire-and-forget extraction (lower latency, but outside the graph, not
  checkpointed, harder to test) — rejected for P1, kept as a documented fallback.
- Extending the journal sub-agent's tool instead of a dedicated node — rejected:
  keeps writes LLM-discretionary, the gap we are closing.

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| (pending) per-task | see PLAN.md `<verify>` rows | — | filled during execution |

### Rollback

- Revert code: `git revert <sha>` (no migration; store schema unchanged).
