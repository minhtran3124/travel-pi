# state-md-auto-update-on-merge — Summary

Lane: high-risk
Confidence: high
Reason: hard gate high-blast (edits .claude/hooks/state-breadcrumb.sh) plus a new CI workflow with contents:write that pushes to main; scope explicitly chosen by the user (A + B).
Flags: high-blast, workflow-engine, existing behavior, weak proof
Affects: .github/workflows (new post-merge job), .claude/hooks/state-breadcrumb.sh, specs/STATE.md, .claude/runtime/run_state.py (caller only)
Input-type: harness improvement
Route: brainstorming (approach already approved in research) → xia2 (Deep) → writing-plans → sibling worktree → implement → correctness + intent review → PR
Escalate: no (hard gate narrowed by the user's explicit A + B choice; one interpretation)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> hien tai sau khi PR dc merge thi file STATE.md luon bi outdate, ko dc update kip thoi. hay suy nghi tim cach nao do (vd nhu tao CI job) de auto update sau khi PR dc merge? research cho van de nay di

(Research proposed A: a GitHub Action on PR merge that transitions the spec's RUN.json
`ready_to_merge → shipped` via `run_state.py` and updates `specs/STATE.md` — the Recent Specs row,
and the Active Spec block only when its slug matches — pushing straight to `main`; B: move the
SessionEnd hook's "Session End Log" out of tracked `specs/STATE.md` into a gitignored
`.harness-state/` file; C: backfill the 22 runs stuck at `ready_to_merge`.)

> A + B

## What changed

A new `state-on-merge` workflow runs when a PR merges into `main`: it finds the PR's spec, appends the
`ready_to_merge → shipped` event (merge sha, `event_id: pr-<N>-merged`) to `events.jsonl`, rewrites
`RUN.json`, refreshes the spec's Recent Specs row in `specs/STATE.md` (and the Active Spec block when
it is that spec), and pushes to `main` as github-actions[bot]. The logic is the stdlib script
`.github/scripts/state_on_merge.py`. STATE.md's 2,080-line Session End Log is gone: the (local,
git-excluded) SessionEnd hook now writes to the gitignored `.harness-state/session-log.md`, and the
existing 300 entries were moved there in the main checkout.

### Rationale

Nothing owned the post-merge hop: finishing-a-development-branch stops at `ready_to_merge` and a
human merges, so only a merge-triggered job can close it. The harness engine is not in git, so the
CI script mirrors the engine's chain invariants and `project()`, and a test proves its output
against the real engine wherever the harness is installed.

### Alternatives considered

- Bot opens a PR instead of pushing — auto-merge is disabled on the repo, so it recreates the manual PR it is meant to remove.
- Local post-merge hook / `gh pr merge` wrapper — misses merges done in the GitHub web UI.
- Derive Recent Specs from RUN.json at read time (stop tracking the table) — cleanest, but a larger change; deferred.
- C (backfill 22 stuck runs) — not chosen by the user this round.

### Deviations

- Rule 1 (review CR fixes, correctness review PASS-WITH-FIXES): a later PR touching an old run's RUN.json no longer ships it under the wrong PR (branch match first; RUN.json-only resolution requires the run's `pr.opened` metadata to name this PR); STATE.md is left alone unless a run actually shipped; table cells split on unescaped pipes only; Slug match ignores a trailing HTML comment; push loop aborts a conflicting rebase with a clear error. Not fixed (low): CRLF newline style, repeated `merged via` prefixes on re-merged slugs.
- Rule 3: `.gitignore` `scripts/` ignored `.github/scripts/`; added `!.github/scripts/`.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| script + workflow tests | `.venv/bin/python -m pytest .github/scripts -q` | 0 | 23 passed | SC-1 |
| engine-backed chain check | `.venv/bin/python -m pytest .github/scripts -q -k engine` | 0 | 2 passed, not skipped (real run_state.py + real gh-200 chain) | SC-2 |
| workflow shape | `.venv/bin/python -m pytest .github/scripts -q -k workflow` | 0 | trigger, fork guard, job-scoped write, env-only inputs | SC-3 |
| no log in STATE.md | `python3 -c "import sys; sys.exit('## Session End Log' in open('specs/STATE.md').read())"` | 0 | 2132 → 53 lines | SC-4 |
| .harness-state ignored | `git check-ignore -q .harness-state/session-log.md` | 0 | | SC-5 |
| hook writes to .harness-state | `bash specs/state-md-auto-update-on-merge/check_hook.sh` | 0 | idempotent; STATE.md untouched | SC-6 |
| lint | `.venv/bin/ruff check .github/scripts && .venv/bin/ruff format --check .github/scripts` | 0 | | |

### Not auto-verified

- The workflow on real GitHub (event payload, `gh api` on a private repo with `pull-requests: read`, bot push to main) — reached traceability (shape test only); it runs for the first time on this PR's own merge.
- The hook change is local to this machine (`.claude/` is git-excluded); a harness redeploy with `--overwrite-conflicts` would revert it — reached truth locally (SC-6), not durable.
- CI does not run `.github/scripts` tests (ci.yml covers apps/api and apps/web only); the engine tests skip wherever `.claude/` is absent.

### Rollback

- `git revert <merge-sha>` — removes the workflow, script, gitignore lines, and restores STATE.md's log section.
- Hook (local, untracked): `cp .harness-state/state-breadcrumb.sh.orig .claude/hooks/state-breadcrumb.sh`.
- A bad bot commit on main: `git revert <bot-sha>` (it touches only specs/<slug>/RUN.json, events.jsonl, specs/STATE.md).

### Harness-Delta

- backlog: the root `.gitignore` pattern `scripts/` silently ignores any `scripts/` dir (caught `.github/scripts/`; fixed with a negation here).
- backlog: harness-skills' `hooks/state-breadcrumb.sh` still writes to STATE.md for every other project; port this change upstream if wanted.
