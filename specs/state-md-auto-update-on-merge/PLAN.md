# state-md-auto-update-on-merge — Plan

status: approved

## 1. Goal

After a PR merges into `main`, a workflow marks its spec shipped (events.jsonl + RUN.json) and
refreshes `specs/STATE.md` without a manual PR; the SessionEnd breadcrumb no longer dirties STATE.md.

## Global Constraints

- The CI script is stdlib-only Python ≥3.10 and must not import anything under `.claude/`.
- Events/RUN.json written by the script must pass the real engine's `validate_chain` and equal `project()`.
- The workflow never fails for a PR without a resolvable spec; untrusted PR fields reach `run:` only via `env:`.
- Hook edits are local-only (`.claude/` is excluded from git); the PR carries no `.claude/` file.

## 2. Tasks

### Task 1.1 — Post-merge script + tests (wave 1)

- **Files:** .github/scripts/state_on_merge.py, .github/scripts/test_state_on_merge.py
- **Action:** Implement slug resolution, the ready_to_merge→shipped append + projection, and the
  STATE.md row / Active Spec refresh; idempotent on re-run. Tests cover each, plus an engine-backed
  chain check (skipped when `.claude/runtime/run_state.py` is absent).
- **Verify:** `.venv/bin/python -m pytest .github/scripts -q`
- **Done:** all tests pass, engine-backed test not skipped locally.
- **Criteria:** SC-1, SC-2
- **Interfaces:** Consumes PR number, merge sha, head ref, changed-files list. Produces `.github/scripts/state_on_merge.py`.

### Task 1.2 — Session log out of STATE.md (wave 1)

- **Files:** .gitignore, specs/STATE.md
- **Action:** Ignore `.harness-state/`; delete the "Session End Log" section and fix the Notes bullets.
- **Verify:** `git check-ignore -q .harness-state/session-log.md`
- **Done:** STATE.md has no log section; `.harness-state/` ignored.
- **Criteria:** SC-4, SC-5
- **Interfaces:** Consumes current STATE.md. Produces `specs/STATE.md`.

### Task 2.1 — Workflow (wave 2)

- **Files:** .github/workflows/state-on-merge.yml
- **Action:** `pull_request: closed` into main + merged + same-repo guard; job-level `contents: write`;
  list PR files via `gh api`; run the script; commit as github-actions[bot]; push with rebase retry.
- **Verify:** `.venv/bin/python -m pytest .github/scripts -q -k workflow`
- **Done:** workflow test passes.
- **Criteria:** SC-3
- **Interfaces:** Consumes `.github/scripts/state_on_merge.py`. Produces `.github/workflows/state-on-merge.yml`.

### Task 2.2 — Local hook writes to .harness-state (wave 2, untracked)

- **Files:** .claude/hooks/state-breadcrumb.sh
- **Action:** Write breadcrumbs to `<project>/.harness-state/session-log.md` (create dir), idempotency
  grep on that file; apply to the main checkout's live copy and migrate the existing log there.
- **Verify:** `bash specs/state-md-auto-update-on-merge/check_hook.sh`
- **Done:** hook appends to `.harness-state/session-log.md` and leaves STATE.md untouched.
- **Criteria:** SC-6
- **Interfaces:** Consumes SessionEnd stdin JSON. Produces `.harness-state/session-log.md`.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
| --- | --- | --- | --- |
| SC-1 | Script resolves slug, ships the run, refreshes STATE.md, idempotently | `.venv/bin/python -m pytest .github/scripts -q` | exit 0 |
| SC-2 | Written chain is valid for the real engine and RUN.json equals its projection | `.venv/bin/python -m pytest .github/scripts -q -k engine` | exit 0 |
| SC-3 | Workflow triggers only on merged same-repo PRs into main, with job-scoped write and env-passed inputs | `.venv/bin/python -m pytest .github/scripts -q -k workflow` | exit 0 |
| SC-4 | STATE.md carries no Session End Log | `python3 -c "import sys; sys.exit('## Session End Log' in open('specs/STATE.md').read())"` | exit 0 |
| SC-5 | `.harness-state/` is gitignored | `git check-ignore -q .harness-state/session-log.md` | exit 0 |
| SC-6 | Hook appends to `.harness-state/session-log.md`, not STATE.md | `bash specs/state-md-auto-update-on-merge/check_hook.sh` | exit 0 |
