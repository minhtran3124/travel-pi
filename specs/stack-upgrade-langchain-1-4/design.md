---
slug: stack-upgrade-langchain-1-4
doc: design
created: 2026-09-18
status: approved
---

# Design — stack-upgrade-langchain-1-4

## Goal

Raise the LangChain-stack floors in `apps/api/requirements-ai.txt` to the minimums `deepagents 0.7.15`
declares, so a later `trip-research-deep-agent` feature adds one dependency instead of moving the
whole stack. `deepagents` itself is **not** added here.

## Decision

Floors only (no exact pins, no new packages):

| Package | Before | After | Why |
|---|---|---|---|
| `langchain` | `>=1.0,<2.0` | `>=1.4.1,<2.0` | deepagents floor |
| `langchain-core` | (transitive) | `>=1.6.3,<2.0` | deepagents floor; explicit because we import from it directly |
| `langgraph` | `>=1.0,<2.0` | `>=1.2.11,<2.0` | `langchain 1.4.1` requires it |
| `langchain-anthropic` | `>=1.0,<2.0` | `>=1.7.2,<2.0` | deepagents floor |
| `langchain-google-genai` | `>=4.0,<5.0` | `>=4.4.0,<5.0` | deepagents floor |

Everything else (`langgraph-prebuilt`, checkpointers, `langchain-openai`, `langchain-postgres`,
`deepeval`, `agentevals`) keeps its range; the resolver moves them only if forced.

## Design fork considered

- **Exact pins + lockfile** for the AI stack — a genuinely different approach (reproducible
  builds, but a new maintenance loop and a repo-convention change). Rejected for this PR: out of
  scope; the repo's convention is justified floors, and the Docker image build is the
  reproducibility check.
- **Add `deepagents` now** — rejected; mixing a stack move with a new runtime dependency makes any
  regression ambiguous.

## Proof strategy

The stack is exercised through behaviour, not import smoke: full SQLite suite on the resolver's
Python 3.12 result (matches the Docker image), the Postgres suite in Docker on the rebuilt image,
and the 18-case `eval-smoke` against the live agent, compared with a baseline run on the old stack.
Deprecation-warning summaries are diffed old vs new so silent behaviour changes surface.

## Known environment traps (not caused by this change)

- Running pytest from `apps/api/` loads `apps/api/.env` (dashboard basic-auth creds, real
  provider keys, Postgres URL) and reddens ~59 tests on **both** stacks. Comparisons run from a
  cwd without `.env`, with `--rootdir apps/api -c apps/api/pyproject.toml`.
- `make test-docker` tears down the dev stack (`down -v` on the shared compose project); the
  Postgres suite runs under `-p apitest` instead.
