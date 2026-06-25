---
problem_type: bug
module: harness/hooks
tags: check-untracked-py, hook, claude-dir, path-pattern, grep, leading-slash, commit
severity: standard
applicable_when: Committing in a repo whose `.claude/` harness tree is untracked and contains `.py` files (e.g. skills/visual-planner/*.py), tripping `check-untracked-py.sh`
affects:
  - .claude/hooks/check-untracked-py.sh
supersedes: null
confidence: high
confirmed_at: 2026-06-23
---
## Problem

`check-untracked-py.sh` (PreToolUse on `git commit`/`git push`) denies the commit with
"Untracked .py not staged (would break CI imports)" listing harness files such as
`.claude/skills/visual-planner/render_plan.py`. These are intentionally-untracked harness files,
unrelated to the feature being committed — the gate blocks on noise.

## Root Cause

The hook tries to exclude the harness tree:

```bash
FILES=$(git ls-files --others --exclude-standard | grep -E '\.py$' | grep -v '/\.claude/')
```

`git ls-files` emits **repo-relative** paths with **no leading slash**, so a root-level harness
file is `.claude/skills/.../render_plan.py`. The exclusion pattern `/\.claude/` requires a slash
**before** `.claude`, which only matches a *nested* `foo/.claude/...`. Root-level `.claude/` has
no preceding slash, so it slips past the filter and trips the gate.

## Fix

Anchor the exclusion to also match the path start (high-blast `.claude/hooks/*` — Rule 4, needs
human approval before editing; not auto-applied):

```bash
# match .claude/ whether at the repo root or nested
grep -vE '(^|/)\.claude/'
```

## Regression Test

[none] — shell hook. Verify manually: with an untracked `.claude/**/*.py` present, run a commit
and confirm it is no longer denied; with an untracked `app/**/*.py` present, confirm it IS still
denied.

## Prevention

Workaround that touches no tracked file or hook (used in `router-metadata-dedup`): add the
harness tree to git's **local** exclude so `--exclude-standard` skips it —

```bash
grep -qxF '.claude/' .git/info/exclude || printf '.claude/\n' >> .git/info/exclude
```

Reversible (delete the line); matches the hook's clear intent. Filed as a ratchet candidate in
`docs/harness-experimental/improvement-backlog.md`.

## Related

- docs/solutions/harness/commit-gate-bare-python.md
- docs/solutions/harness/public-contract-gate-warn-only.md
