---
slug: stack-upgrade-langchain-1-4
status: shipped
owner: minhtran3124
created: 2026-09-18
---

# stack-upgrade-langchain-1-4 — raise LangChain floors for deepagents 0.7.15

## 1. Motivation

See `design.md`. One manifest file changes; the proof is the whole agent harness still behaving.

## 2. Global Constraints

- Only `apps/api/requirements-ai.txt` changes under `apps/`; no code edits unless a suite fails
  because of the upgrade (then the fix is its own task, appended here with its SC).
- `deepagents` is never installed in this PR.
- Every comparison runs old stack vs new stack under the **same** environment (no `.env` in cwd).
- Stage `specs/stack-upgrade-langchain-1-4/SUMMARY.md` with every commit so the risk hook resolves
  the `high-risk` lane from this spec.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | The bumped manifest resolves cleanly on Python 3.12 (Docker's interpreter) with `langchain>=1.4.1`, `langchain-core>=1.6.3`, `langgraph>=1.2.11` | `uv venv --python 3.12 /tmp/sc1 -q && uv pip install --python /tmp/sc1/bin/python -r apps/api/requirements.txt -q && uv pip check --python /tmp/sc1/bin/python` | exit 0 |
| SC-2 | Full BE suite passes on SQLite on the new stack, from a cwd without `.env`, with the same pass count as the old stack | `mkdir -p /tmp/sc2 && cd /tmp/sc2 && PYTHONPATH=$OLDPWD/apps/api /tmp/sc1/bin/python -m pytest $OLDPWD/apps/api/tests -q -p no:cacheprovider --rootdir $OLDPWD/apps/api -c $OLDPWD/apps/api/pyproject.toml` | exit 0; `2806 passed, 6 skipped` |
| SC-3 | Full BE suite passes on Postgres in Docker on the rebuilt image | `cd apps/api && docker compose -p apitest -f docker-compose.test.yml build tests && docker compose -p apitest -f docker-compose.test.yml run --rm --entrypoint "" tests sh -c "alembic upgrade head >/dev/null && mkdir -p /tmp/run && cd /tmp/run && PYTHONPATH=/app python -m pytest /app/tests -q -p no:cacheprovider --rootdir /app -c /app/pyproject.toml"; docker compose -p apitest -f docker-compose.test.yml down -v` | exit 0 |
| SC-4 | The repo `.venv` runs the new stack and the app imports | `cd apps/api && ../../.venv/bin/python -c "from importlib.metadata import version as v; from packaging.version import Version as V; assert V(v('langchain'))>=V('1.4.1') and V(v('langgraph'))>=V('1.2.11') and V(v('langchain-core'))>=V('1.6.3'); import app.main; print(v('langchain'), v('langgraph'), v('langchain-core'))"` | exit 0 |
| SC-5 | `eval-smoke` on the new stack keeps every capability above its threshold that was above threshold on the old-stack baseline run | `cd apps/api && ../../.venv/bin/python -m eval --suite smoke --out eval/reports/latest.json --html eval/reports/latest.html` | exit 0; no capability regresses vs the baseline report |
| SC-6 | No new deprecation warning from `langchain*`/`langgraph*` appears in the suite that was absent on the old stack | `python3 -c "import re;f=lambda p:set(re.findall(r'lang\w[A-Za-z_./]*\.py:\d+.*',open(p).read()));d=f('/tmp/warn-new.txt')-f('/tmp/warn-base.txt');print(d);raise SystemExit(1 if d else 0)"` | exit 0 (empty set), or each new line explained in SUMMARY |

### Task 1.1 — Raise the floors (wave 1)

- **Files:** apps/api/requirements-ai.txt
- **Action:** Bump `langgraph`, `langchain`, `langchain-anthropic`, `langchain-google-genai`
  floors and add an explicit `langchain-core>=1.6.3,<2.0` line, with a comment naming the
  reason (deepagents 0.7.15 floors) and the spec slug.
- **Verify:** `cd apps/api && grep -cE '^(langchain>=1.4.1|langchain-core>=1.6.3|langgraph>=1.2.11|langchain-anthropic>=1.7.2|langchain-google-genai>=4.4.0)' requirements-ai.txt | grep -qx 5`
- **Done:** all five floors present; `uv pip check` clean on 3.12.
- **Criteria:** SC-1
- **Interfaces:** Consumes deepagents 0.7.15 METADATA floors. Produces `apps/api/requirements-ai.txt`.

### Task 1.2 — Behavioural proof on both interpreters (wave 2)

- **Files:** specs/stack-upgrade-langchain-1-4/SUMMARY.md
- **Action:** Run SC-2 (SQLite, py3.12), SC-3 (Postgres, Docker), SC-6 (warnings diff) and record
  each row with exit code in `SUMMARY.md ### Verify`.
- **Verify:** `python3 .claude/scripts/verify_summary.py --lane stack-upgrade-langchain-1-4`
- **Done:** every SC-2/3/6 row present with exit 0 (or an explained diff for SC-6).
- **Criteria:** SC-2, SC-3, SC-6
- **Interfaces:** Consumes the resolved venv from Task 1.1. Produces `specs/stack-upgrade-langchain-1-4/SUMMARY.md`.

### Task 1.3 — Upgrade the repo venv and run eval-smoke (wave 3)

- **Files:** specs/stack-upgrade-langchain-1-4/SUMMARY.md, specs/stack-upgrade-langchain-1-4/research-brief.md
- **Action:** Capture the old-stack `eval-smoke` baseline first, then
  `uv pip install --python .venv/bin/python -r apps/api/requirements.txt`, rerun `eval-smoke`,
  compare per capability, and write the comparison plus the changelog scan into
  `research-brief.md`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -c "import langchain;assert langchain.__version__.startswith('1.4')"`
- **Done:** SC-4 and SC-5 rows recorded; no capability regression, or each regression triaged.
- **Criteria:** SC-4, SC-5
- **Interfaces:** Consumes the baseline report. Produces `specs/stack-upgrade-langchain-1-4/research-brief.md`.

## Status log

- 2026-09-18 — shipped on branch `chore/stack-upgrade-langchain-1-4` (commits 707aa9b3, 3bebffd8 + this record); correctness + intent reviews PASS, 0 blocking.
