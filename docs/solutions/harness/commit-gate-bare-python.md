---
problem_type: bug
module: harness/hooks
tags: commit-quality-gate, hook, python, path, venv, portability
severity: standard
applicable_when: Committing app/ changes in a shell where `python` is not on PATH (only `.venv/bin/python` or `python3`)
affects:
  - .claude/hooks/commit-quality-gate.sh
supersedes: null
confidence: high
confirmed_at: 2026-06-18
---
## Problem

`commit-quality-gate.sh` runs the affected-test re-check with a **bare `python`**
(`OUTPUT=$(python -m pytest …)`, ~line 153). On macOS / a uv-style venv there is no `python`
on PATH — only `.venv/bin/python` (and `python3`). The gate then fails (or the test step
errors) on every commit unless the committer prepends the venv to PATH.

## Root Cause

The hook is inconsistent about the interpreter: the evidence-recheck block guards on
`command -v python3` (lines ~91–92), but the pytest re-run hardcodes `python`. So a machine
without a `python` shim trips the gate even though `python3` / the venv interpreter exist.

## Fix

Resolve the interpreter once and reuse it, e.g. near the top of the hook:

```bash
PY="$(command -v python3 || command -v python)"
[[ -x .venv/bin/python ]] && PY=.venv/bin/python
# …
OUTPUT=$("$PY" -m pytest $TEST_FILES -x -q --tb=short --no-cov -m "not integration" -p no:cacheprovider 2>&1)
```

> NOTE: `.claude/hooks/*` is a high-blast-radius file (auto-runs every session) — per
> `rules/auto-correct-scope.md` Rule 4 this change needs explicit human approval before
> editing. Not applied automatically.

## Regression Test

[none] — shell hook; verify manually by committing an `app/` change in a shell where `python`
is absent but `python3`/`.venv/bin/python` exist.

## Prevention

Workaround until fixed: prefix the commit with the venv —
`PATH="$(pwd)/.venv/bin:$PATH" git commit …`. Tracked as a ratchet candidate in
`docs/harness-experimental/improvement-backlog.md`.

## Related

- docs/solutions/harness/formatter-strips-unused-import.md
