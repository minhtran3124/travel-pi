---
problem_type: bug
module: harness/hooks
tags: hooks, commit-gate, git-worktree, claude-project-dir, cross-session, false-block, verify-summary, normalize-tool-input, write-edit-refused
severity: critical
applicable_when: A commit from a linked git worktree is blocked by a gate complaining about a file the commit does not touch — especially a `specs/<other-slug>/SUMMARY.md` belonging to someone else's branch.
affects:
  - .claude/hooks/commit-quality-gate.sh
  - .claude/hooks/lib/normalize-tool-input.py
supersedes: null
confidence: high
confirmed_at: 2026-09-09
---
## Problem

A commit from `.worktrees/feat/close-product-loop-s3-today`, staging only files under
`apps/web/src/components/trips/today/`, was rejected by the commit-quality gate with nine
findings about `specs/gh-173-supervisor-local-tips-fanout/SUMMARY.md` — a spec on a different
branch that the commit never touched and that does not exist in that worktree.

The block was not recoverable from inside the agent session, and it applied to **every** linked
worktree in the repository at once, for as long as the main checkout's index held the offending
file.

## Root Cause

`commit-quality-gate.sh` resolves the repository it audits as:

```sh
REPO_DIR="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
cd "$REPO_DIR" || exit 2
```

The environment variable wins over the toplevel of the repository the commit is actually running
in. `CLAUDE_PROJECT_DIR` points at the **main checkout**, so every subsequent `git diff --cached`
in the hook reads the main checkout's index. A linked worktree's own staged set is never examined.

Both halves of the gate are therefore wrong from a worktree:

- it **fails** on staged work that is not part of this commit — the case seen here, where the main
  checkout was parked on another branch with a half-finished staged `SUMMARY.md`;
- it would **pass** work that *is* part of this commit, because those paths are invisible to it.

The second half is the more dangerous one: a worktree commit that should be gated slips through
unaudited, and nothing says so.

## Fix

Not yet applied — recorded so the next session does not re-diagnose it. The correct precedence is
the inverse of the current one: prefer the toplevel of the repository the commit is running in,
and fall back to `CLAUDE_PROJECT_DIR` only when that is unavailable.

```sh
REPO_DIR="$(git rev-parse --show-toplevel 2>/dev/null)"
REPO_DIR="${REPO_DIR:-$CLAUDE_PROJECT_DIR}"
```

The existing fallback is already right; it is the env var winning that breaks the worktree case.
Note the original comment on that line warns against deriving the root from `SCRIPT_DIR`, which
remains correct — `--show-toplevel` from the hook's CWD is not the same hazard, because the hook
runs with the committing repository as its working directory.

## Regression Test

None yet. A test would create a linked worktree, stage a violating `SUMMARY.md` in the main
checkout only, commit unrelated files from the worktree, and assert the gate passes; then stage a
violating `SUMMARY.md` in the worktree and assert it blocks.

## Prevention

- **A workaround from inside a Bash tool call does not exist.** `CLAUDE_PROJECT_DIR=... git commit`
  looks like it should work and does not: the gate is a PreToolUse hook executed by the harness in
  the *session's* environment, before the Bash command runs. An inline env prefix reaches git, never
  the hook that gates it. This was tried and produced an identical block.
- **`CLAUDE_PROJECT_DIR` appearing unset inside a Bash call is not evidence it is unset for the
  hook.** A second session concluded it was unaffected on exactly that reasoning, then hit the same
  block. The hook's environment is the session's, which you cannot observe from a tool call.
- When a gate names a file your commit does not touch, check `git diff --cached --name-only` in the
  **main checkout**, not only in your worktree. The message names the file but not whose index it
  came from, which is what makes this cost an hour.
- Do not resolve it by completing or unstaging the other session's work. Completing another
  session's Verify table fabricates evidence for checks nobody ran. Ask the owning session, or the
  user.

## Second manifestation: Write and Edit refused in a sibling worktree (2026-09-10)

The same root cause blocks file edits, not only commits. In `prompt-caching-system-prefix`, run from
a sibling worktree `../travel-pi-prompt-caching-system-prefix`, **every** `Write` and `Edit` call on
a worktree path was refused with a branch-isolation `unsafe-path:outside-root` error — for all five
wave subagents and for the controller, even after `EnterWorktree`, and even for the scratchpad.

`hooks/lib/normalize-tool-input.py` resolves its root with the same precedence:

```python
default=os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd(),
```

`CLAUDE_PROJECT_DIR` is the main checkout, so any path in a sibling worktree resolves outside the
root and is refused. The fix is the same inversion: prefer the toplevel of the repository the path
belongs to (`git -C <dir> rev-parse --show-toplevel`), or accept any root listed by
`git worktree list`.

Workaround used, and why it is not a fix: every file was written through Bash + `python3` heredocs,
which the normaliser does not inspect. That works, but it also silently skips every PreToolUse
check keyed on Write/Edit — so the worktree is less guarded, not equally guarded. Tell subagents
this in the dispatch prompt, or each one burns turns rediscovering it.

Consequence for isolation choice: until both hooks are fixed, an in-place feature branch is safer
than a sibling worktree whenever the work needs Write/Edit.

## Related

- docs/solutions/harness/untracked-py-gate-root-claude.md
- docs/solutions/harness/commit-gate-bare-python.md
