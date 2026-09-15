#!/usr/bin/env bash
# SC-6: the SessionEnd hook appends to .harness-state/session-log.md and never touches STATE.md.
# Run from the repo root. The hook is harness-local (.claude/ is excluded from git).
set -euo pipefail
hook=".claude/hooks/state-breadcrumb.sh"
test -f "$hook" || { echo "missing $hook"; exit 1; }
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/specs"; printf '# Workflow State\n' > "$tmp/specs/STATE.md"
before=$(cat "$tmp/specs/STATE.md")
for _ in 1 2; do  # second run must be a no-op (idempotent per session_id)
  printf '{"session_id":"sc6-test","cwd":"%s"}' "$tmp" | CLAUDE_PROJECT_DIR="$tmp" bash "$hook"
done
test "$(grep -c 'session_id: sc6-test' "$tmp/.harness-state/session-log.md")" = 1
test "$(cat "$tmp/specs/STATE.md")" = "$before"
echo "SC-6 ok"
