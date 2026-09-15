# state-md-auto-update-on-merge — Design

Status: APPROVED (user chose A + B after research, 2026-09-15; hook location = local travel-pi copy)

## Problem

`specs/STATE.md` and each spec's `RUN.json` go stale after a PR merges. `finishing-a-development-branch`
stops at "PR opened" (`ready_to_merge`); the harness defines `ready_to_merge → shipped` but nothing
runs it after merge, so 22 runs sit at `ready_to_merge` and every merge needs a hand-made STATE.md PR
(#207, #208). Separately, the SessionEnd hook appends a breadcrumb to the *tracked* STATE.md on every
session, so the file is dirty in every checkout.

## Decision

**A — post-merge workflow.** `.github/workflows/state-on-merge.yml` runs on `pull_request: closed`
into `main` when `merged == true`. It resolves the PR's spec slug, appends the
`ready_to_merge → shipped` event (`event_id: pr-<N>-merged`, `sha` = merge commit) to
`specs/<slug>/events.jsonl`, rewrites `RUN.json` as the engine's projection, refreshes STATE.md
(Recent Specs row always; Active Spec block only when its Slug is the merged slug), then commits as
`github-actions[bot]` and pushes straight to `main` with a rebase-retry loop.

The logic lives in a self-contained stdlib script, `.github/scripts/state_on_merge.py`, because the
harness (`.claude/`, incl. `runtime/run_state.py`) is excluded from git via `.git/info/exclude` and
therefore absent in CI. The script mirrors the engine's chain invariants and `project()` exactly; a
test validates its output with the real engine whenever `.claude/runtime/run_state.py` is present.

**Slug resolution.** Exactly one `specs/<slug>/RUN.json` in the PR's changed files → that slug.
Otherwise strip the `<type>/` prefix from the head branch and use it if `specs/<slug>/` exists.
Otherwise skip (chore/docs PRs, specs without a run) — never fail the job.

**B — session log out of git.** The local hook writes to `.harness-state/session-log.md`
(gitignored); STATE.md drops its "Session End Log" section (history moved into that local file).

## Out of scope

- C (backfill of the 22 stuck runs).
- Changing the harness source in `harness-skills` (user chose the local copy).
- Generating Recent Specs from RUN.json at read time.
