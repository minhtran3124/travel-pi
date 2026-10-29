#!/bin/bash
# PostToolUse (Write|Edit): run `ruff check --fix` and `ruff format` on the edited Python file.
# Reads the hook JSON from stdin. Never blocks: always exits 0, ruff output goes to stderr.
set -u

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
RUFF="$ROOT/.venv/bin/ruff"
[ -x "$RUFF" ] || RUFF=$(command -v ruff) || exit 0
command -v jq >/dev/null 2>&1 || exit 0

FILE=$(jq -r '.tool_input.file_path // empty' 2>/dev/null)
[ -n "$FILE" ] || exit 0
case "$FILE" in
  "$ROOT"/apps/api/*.py) ;;   # only the backend, where ruff is configured
  *) exit 0 ;;
esac
[ -f "$FILE" ] || exit 0

cd "$ROOT/apps/api" || exit 0
"$RUFF" check --fix --quiet "$FILE" >&2
"$RUFF" format --quiet "$FILE" >&2
exit 0
