# agent-eval-pipeline — Escalations

## 2026-07-13 — hard gate: `external-provider` (dependency manifest)

**Trigger.** `.claude/hooks/risk-corroboration.sh` blocked the task-1.1 commit: the staged diff
contains `apps/api/evalkit/pyproject.toml`, and the path rule
`(requirements[^/]*\.txt|package\.json|pyproject\.toml|go\.mod|Gemfile)$` maps any dependency
manifest to the `external-provider` hard gate.

**What is actually in the diff.**

- `apps/api/evalkit/pyproject.toml` — manifest for a **local** package (`agent-evalkit`) that
  lives inside this repo. Its only dependency is `pydantic>=2`, already a project dependency.
- Later, task 2.2 will pin `agentevals` (langchain-ai, MIT) in `requirements-ai.txt` — a
  **library**, installed from PyPI into the existing venv.

**No new external service.** Nothing calls a new provider, broker, webhook target, or paid API.
`auto-correct-scope.md` classifies a new library pin as **Rule 3 (auto-fix blocking)**; Rule 4's
STOP condition is "introducing a new external *service* dependency", which this is not. The hook's
path rule cannot draw that distinction.

**Human authorization on record.** The user approved the plan that names both artifacts:

> "ok, chot huong. Nhưng tôi muốn build theo hướng 1 cách sạch sẽ nhất để sau này cải tiến nó lên
> thành 1 mcp hoặc tool tương tự đê adopt cho các dự án khác" — 2026-07-13

The standalone-installable `evalkit` package (hence its own `pyproject.toml`) is the direct
consequence of that instruction; `agentevals` was named in the plan summary the user approved.

**Resolution (taken).** Lane upgraded `normal → high-risk` in `SUMMARY.md` — the harness's own
mechanical rule (detectable hard gate ⇒ high-risk) is followed rather than argued with. Upgrading
is always permitted; only a *downgrade* would need a human. Ceremony that the high-risk lane
requires is in place: `research-brief.md`, two design docs, `PLAN.md`, a filled `### Verify` table,
and a `### Rollback` block. `RISK_WARN_CATEGORIES` was not usable: PreToolUse hooks read the Claude
Code process environment, not the command's, so an agent cannot loosen a category in-band.

**Open for the human (non-blocking).** If you would rather the manifest gate not fire for
library-only changes, the fix belongs in the hook (split `external-provider` into
`external-service` (keyword) vs `dependency-manifest` (path, warn-mode)), not in this spec. Logged
as a Harness-Delta backlog item in `SUMMARY.md`.
