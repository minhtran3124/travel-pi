# Solutions Index

O(1) lookup of all entries in `docs/solutions/`. Read this first when searching for prior art.

## Entries

| Slug | Category | Module | Tags | Type | Confidence | Confirmed |
|---|---|---|---|---|---|---|
| [operate-from-subdir](monorepo/operate-from-subdir.md) | monorepo | monorepo | monorepo, turborepo, pnpm, relocation, python | knowledge | high | 2026-06-26 |
| [phase1-architecture-decisions](monorepo/phase1-architecture-decisions.md) | monorepo | monorepo | monorepo, turborepo, pnpm, nextjs, tanstack-query | decision | high | 2026-06-26 |
| [pnpm-node-floor-mismatch](ci/pnpm-node-floor-mismatch.md) | ci | ci | ci, pnpm, node-version, github-actions, packagemanager | bug | high | 2026-06-26 |
| [agent-sse-on-nextjs](streaming/agent-sse-on-nextjs.md) | streaming | streaming | sse, nextjs, streaming, fetch-readablestream, proxy-buffering | knowledge | high | 2026-06-26 |
| [wave-shared-file-partition](harness/wave-shared-file-partition.md) | harness | harness | subagent-parallelism, wave-parallelism, blast-radius, test-infra, shared-types | failure | high | 2026-06-26 |
| [public-contract-gate-warn-only](harness/public-contract-gate-warn-only.md) | harness | harness/intake | risk-corroboration, public-contract, feature-intake, openapi, lane | knowledge | high | 2026-06-23 |
| [untracked-py-gate-root-claude](harness/untracked-py-gate-root-claude.md) | harness | harness/hooks | check-untracked-py, hook, claude-dir, path-pattern, grep | bug | high | 2026-06-23 |
| [formatter-strips-unused-import](harness/formatter-strips-unused-import.md) | harness | harness/editing | postusetool-formatter, ruff, autoflake, fastapi, imports | failure | high | 2026-06-18 |
| [commit-gate-bare-python](harness/commit-gate-bare-python.md) | harness | harness/hooks | commit-quality-gate, hook, python, path, venv | bug | high | 2026-06-18 |
| [local-postgres-checkpointer](agent/local-postgres-checkpointer.md) | agent | agent/checkpointer | checkpointer, langgraph, postgres, memory-saver, conversation-persistence, uvicorn-reload | knowledge | high | 2026-06-27 |

## Critical Patterns

`critical-patterns.md` is always read regardless of query domain — do not skip it.

## Maintenance

- `/compound` appends a row here on every new solution file
- Downgrade confidence on rows whose `confirmed_at` has aged past the decay thresholds (see README.md)
- Remove rows only when the underlying file is deleted (add a tombstone line if needed)
