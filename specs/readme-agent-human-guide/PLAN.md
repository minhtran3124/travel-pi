---
slug: readme-agent-human-guide
status: shipped
owner: Minh Tran
created: 2026-08-28
---

# Root README for humans and coding agents

## Global Constraints

- Keep the update limited to documentation; do not change application behavior, dependencies, or generated files.
- Treat repository manifests, Makefiles, and implementation docs as the source of truth for commands and architecture.
- Preserve the user’s unrelated worktree changes.

## 1. Motivation

The root README currently gives basic commands but does not clearly explain the product
boundary, the AI-agent architecture, or the contributor workflow. It should become the
reliable first stop for a developer or coding agent without duplicating the detailed docs.

## 2. Non-goals

- Rewriting app-level READMEs or implementation documentation.
- Changing runtime configuration, deployment, authentication, or code.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
| --- | --- | --- | --- |
| SC-1 | The root README states what is real versus synthetic and introduces the AI-agent architecture. | `rg -q "## Product boundaries" README.md` | exit 0 |
| SC-2 | The root README gives a runnable local setup and contributor workflow with links to authoritative detail. | `rg -q "## Working with the codebase" README.md` | exit 0 |
| SC-3 | The plan follows the repository plan contract. | `python3 .claude/scripts/check_plan_contract.py specs/readme-agent-human-guide/PLAN.md` | exit 0 |

## 4. Tasks

### Task 1.1 — Rewrite the root entry point

- **Criteria:** SC-1, SC-2
- **Interfaces:** Consumes existing Makefiles, manifests, and project documentation; produces an accurate, navigable `README.md`.
- **Files:** README.md
- **Action:** Replace the minimal setup-focused README with a concise product overview, clear operational boundaries, verified local setup/run/test commands, architecture orientation, and tailored reading paths for humans and coding agents.
- **Verify:** `rg -q "## Working with the codebase" README.md`
- **Done:** A new contributor can understand the system, run it locally, and locate the authoritative detail without needing to infer undocumented behavior.

### Task 1.2 — Record documentation evidence

- **Criteria:** SC-3
- **Interfaces:** Consumes the README update and verification results; produces `specs/readme-agent-human-guide/SUMMARY.md`.
- **Files:** specs/readme-agent-human-guide/SUMMARY.md
- **Action:** Record the scope decision, rationale, verification evidence, and rollback path after completing the documentation update.
- **Verify:** `python3 .claude/scripts/verify_summary.py readme-agent-human-guide --check`
- **Done:** The documentation change has a durable, machine-checkable audit record.

## 5. Risks

- Documentation can drift from runtime behavior; mitigate by deriving commands from committed Makefiles, manifests, and environment examples.
- Detailed agent internals can go stale quickly; link to `WORKFLOW.md` instead of duplicating it.

## 6. Status Log

- 2026-08-28 — Shipped. Rewrote the root contributor entry point and validated its plan and internal links.
