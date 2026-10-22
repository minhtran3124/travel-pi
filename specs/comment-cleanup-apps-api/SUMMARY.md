# comment-cleanup-apps-api — Summary

Lane: high-risk
Confidence: high
Reason: diff touches auth/dashboard-auth/config files (comment-only), which trips the auth/audit hard-gate signal by keyword even though no logic changed.
Flags: auth, audit/security, public-contract
Affects: apps/api (backend-wide, comments/docstrings only)
Input-type: maintenance

### Intent

make the deep review code, check code comment, clean/refactor comment too long or unnecessary. make sure comment is short and ez understanding, dont over comment, put a lot of information that SE will never read them.

(scope narrowed to apps/api backend per user's answer to a clarifying question)

## What changed

Comment-only cleanup across `apps/api/`: removed comments that restated the code, referenced tickets/PRs, or were stale; shortened remaining WHY-bearing comments/docstrings to one line. No logic changed. 332 files touched, -10990/+2155 lines.

### Rationale

Followed the project's own commenting rule (behavior.md / CLAUDE.md): no comment unless the WHY is non-obvious, one short line max. Dispatched to a coding agent (which fanned out into its own sub-agents) since the task spans the whole backend.

### Alternatives considered

- none

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| syntax | `python -m py_compile $(find app scripts -name "*.py")` | 0 | all files compile | |
| lint | `ruff check app scripts` (from apps/api/) | 0 | all checks passed | |
| format | `ruff format --check app scripts` | 0 | 1 file auto-fixed, then clean | |
| full suite (real env) | `python -m pytest -q` (from apps/api/) | 1 | 56 failed, 2545 passed — all env-dependent (real .env creds/keys) | |
| full suite (make test) | `make test` (from apps/api/) | 1 | 59 failed, 2551 passed | |
| full suite on clean tree (stash) | `git stash && make test && git stash pop` | 1 | identical 59 failures on unmodified tree — confirms pre-existing, unrelated to this change | |

### Not auto-verified

- every shortened comment still captures the "real WHY" a human reviewer would want — reached traceability (spot-checked ~10 representative diffs across tools/rag/mcp/core/agents); not exhaustively re-read across all 332 files.

### Rollback

- Undo: `git log --oneline -1 -- apps/api` to find this commit's hash, then `git revert` it. Comment-only diff, no schema/runtime/config impact, so the revert alone fully restores prior state with no follow-up steps.

### Harness-Delta

- backlog: risk-corroboration's auth/audit keyword gate has no allowance for comment-only diffs (it greps changed lines regardless of whether they're comments); a `git diff` restricted to comment/docstring-only hunks would avoid false positives like this one.
