---
problem_type: failure
module: harness/editing
tags: postusetool-formatter, ruff, autoflake, fastapi, imports, header-binding
severity: standard
applicable_when: Adding a new import plus its first usage to a Python file across SEPARATE edits, in a repo whose PostToolUse hook auto-strips unused imports (ruff --fix / autoflake)
affects:
  - .claude/hooks/
  - app/routers/
supersedes: null
confidence: high
confirmed_at: 2026-06-18
---
## Applicable When

Editing Python files (especially FastAPI routers/services) where a PostToolUse formatter
hook removes unused imports on save, and you add an import in one edit and its first
reference in a later, separate edit.

## Symptom

After adding (e.g.) `from fastapi import Header` or `from app.routers import health` in one
Edit, then wiring its first use in a second Edit, the code fails at runtime/import time:

- `NameError` / ruff `F821 undefined name` when the symbol is referenced, **or**
- worse and silent: a FastAPI route param annotated with the now-missing `Header(...)`
  **binds to `None`** instead of reading the header — no error, just wrong behavior
  (e.g. `Idempotency-Key` ignored, or a 404/`NameError` only under request).

Observed **four times in one session** (Header on trip routes, the `health` router import in
`routers/main.py`, and new schema imports), each costing a debug cycle.

## Wrong Approach

Add the import by itself first, then add the usage in a subsequent Edit/tool call:

```python
# Edit 1: add the import  ← formatter runs here, sees it unused, STRIPS it
from fastapi import APIRouter, Header
# Edit 2 (later): add the param that uses Header  ← Header is already gone → NameError/None-bind
```

The PostToolUse formatter fires after **each** edit. Between Edit 1 and Edit 2 the import is
genuinely unused, so the strip is "correct" — but it breaks the half-finished change.

## Why It Failed

`ruff --fix` / autoflake removal of unused imports runs on the intermediate state. The agent's
mental model is "the file after all my edits"; the formatter's model is "the file after THIS
edit." The two disagree precisely in the window where an import exists but its first use does
not. FastAPI compounds it: an annotation referencing a stripped name can degrade to a `None`
default rather than erroring loudly, hiding the breakage until a request exercises it.

## Correct Approach

Add the import **and its first use in the same Edit** (single atomic change), or add the usage
first. Then **verify the import survived** — don't trust the edit:

```bash
# after committing, confirm the symbol is still imported
git show HEAD:app/routers/trips.py | grep -n "Header"
```

When a multi-file feature threads a new symbol, prefer giving an implementer subagent the full
final code for the file in one shot rather than incremental import-then-use edits.

## Guardrail

`proposed:` Make the unused-import auto-strip non-destructive mid-edit — e.g. scope the
PostToolUse ruff/autoflake step to skip `F401` removal (leave it to the commit gate), or run
import-removal only at commit time, not per-edit. Tracked in
`docs/harness-experimental/improvement-backlog.md`.

## Related

- docs/solutions/harness/commit-gate-bare-python.md
