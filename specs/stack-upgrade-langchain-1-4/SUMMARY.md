# stack-upgrade-langchain-1-4 — Summary

Lane: high-risk
Confidence: high
Reason: The change edits a dependency manifest (`apps/api/requirements-ai.txt`) and moves provider SDK floors — the `external-provider` hard gate (block mode) fires; the direction itself has one clear reading.
Flags: external-provider, existing-behavior, weak-proof
Affects: apps/api/requirements-ai.txt (dependency manifest); whole agent harness transitively (app/agents, app/memory, app/rag, app/tools, eval/)
Input-type: maintenance

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> ok, làm bước 1 trước

Bước 1 as stated in the preceding assessment (same session, 2026-09-18):

> 1. Intake `stack-upgrade-langchain-1.4` (high-risk vì high-blast file `requirements-ai.txt`).

Intake argument (verbatim): Upgrade the pinned LangChain stack in apps/api/requirements-ai.txt so that `deepagents` 0.7.15 can be installed later: langchain>=1.4.1, langchain-core>=1.6.3, langgraph>=1.2.11, langchain-anthropic>=1.7.2, langchain-google-genai>=4.4.0 (and any transitive pins that must move with them). Do NOT install deepagents in this PR. Verify with the full BE suite (`make test`), `make test-docker`, and `make eval-smoke`. Slug: stack-upgrade-langchain-1-4

Route: research-brief (dependency resolution + changelog scan) → PLAN.md → using-git-worktrees → execute → correctness/intent review → PR
Escalate: no — hard gate is the dependency manifest itself, which is the entire requested scope; no auth/data/contract touch; single interpretation.

## What changed

`apps/api/requirements-ai.txt` raises the floors `langgraph>=1.2.11`, `langchain>=1.4.1`,
`langchain-anthropic>=1.7.2`, `langchain-google-genai>=4.4.0` and adds an explicit
`langchain-core>=1.6.3` line, with a comment naming why (deepagents 0.7.15 floors). No code, no
`deepagents`. The repo `.venv` and the Docker test image were rebuilt on the new resolution
(langchain 1.4.1 / core 1.6.3 / langgraph 1.2.11 / checkpoint 4.2.0 / anthropic 1.7.2 / genai 4.4.0).
`langchain-openai` stays on 0.3.34 (existing `<1.0` cap) — see research-brief "Decision".

### Rationale

`deepagents 0.7.15` declares floors above the pinned stack (langchain 1.3.11 → ≥1.4.1, core 1.4.8 → ≥1.6.3, langgraph 1.2.6 → ≥1.2.11, anthropic ≥1.7.2, google-genai ≥4.4.0). Upgrading the stack alone, with the full suite + Docker suite + eval-smoke as the gate, isolates regression risk from the later deep-agent feature.

### Alternatives considered

- Install `deepagents` in the same PR — rejected: mixes a stack upgrade with a new runtime dep and makes any regression ambiguous.
- Pin exact versions instead of floors — rejected for now: the repo convention is ranges with explicit floors justified in comments; no lockfile exists.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Resolves on py3.12 (Docker interpreter) | `uv venv --python 3.12 /tmp/sc1 -q && uv pip install --python /tmp/sc1/bin/python -r apps/api/requirements.txt -q && uv pip check --python /tmp/sc1/bin/python` | 0 | "All installed packages are compatible"; langchain 1.4.1 / core 1.6.3 / langgraph 1.2.11 | SC-1 |
| Full suite, SQLite, py3.12, new stack | `mkdir -p /tmp/sc2 && cd /tmp/sc2 && PYTHONPATH=$OLDPWD/apps/api /tmp/sc1/bin/python -m pytest $OLDPWD/apps/api/tests -q -p no:cacheprovider --rootdir $OLDPWD/apps/api -c $OLDPWD/apps/api/pyproject.toml` | 0 | 2806 passed, 6 skipped — identical count to the old stack run under the same command | SC-2 |
| Full suite, Postgres, Docker image rebuilt | `cd apps/api && docker compose -p apitest -f docker-compose.test.yml build tests && docker compose -p apitest -f docker-compose.test.yml run --rm --entrypoint "" tests sh -c "alembic upgrade head >/dev/null && mkdir -p /tmp/run && cd /tmp/run && PYTHONPATH=/app python -m pytest /app/tests -q -p no:cacheprovider --rootdir /app -c /app/pyproject.toml --ignore=/app/tests/core/test_languages.py"; docker compose -p apitest -f docker-compose.test.yml down -v` | 0 | 2808 passed; `test_languages.py` skipped because its `Path(__file__).parents[4]` cannot resolve inside the image (pre-existing since PR #141, fails the same on the old image) | SC-3 |
| Repo `.venv` on the new stack + app imports | `cd apps/api && ../../.venv/bin/python -c "from importlib.metadata import version as v; assert v('langchain')>='1.4.1' and v('langgraph')>='1.2.11' and v('langchain-core')>='1.6.3'; import app.main; print(v('langchain'), v('langgraph'), v('langchain-core'))"` | 0 | prints `1.4.1 1.2.11 1.6.3` | SC-4 |
| eval-smoke, new stack, real provider | `cd apps/api && ../../.venv/bin/python -m eval --suite smoke --out eval/reports/latest.json --html eval/reports/latest.html` | 0 | 19/20 cases, all 9 capabilities above threshold (baseline old stack: 18/20, `journal` below threshold). Per-case flips (`dates-happy-en-01`, `dates-ambiguous-en-02`, `journal-happy-en-01`) reproduced in both directions on the OLD stack across 3 pinned re-runs → LLM noise, not regression | SC-5 |
| No new langchain/langgraph deprecation warnings | `python3 -c "import re;f=lambda p:set(re.findall(r'lang\w[A-Za-z_./]*\.py:\d+.*',open(p).read()));d=f('/tmp/warn-new.txt')-f('/tmp/warn-base.txt');print(d);raise SystemExit(1 if d else 0)"` | 0 | prints `set()`; remaining warning differences are py3.12 vs py3.14 line numbers and a starlette httpx2 notice only on the baseline interpreter | SC-6 |
| Plan contract | `python3 .claude/scripts/check_plan_contract.py specs/stack-upgrade-langchain-1-4/PLAN.md` | 0 | passed | |

### Not auto-verified

- `langchain-openai 0.3.34` against `langchain-core 1.6.3` is an upstream-untested pairing — reached **truth** only through the 20-case `eval-smoke` and the FakeLLM suite; a full judged `make eval-check` was not run (paid).
- `langchain-google-genai 4.4.0` (Gemini default temperature removed in 4.3.0) — reached **provenance** (release notes); no Gemini-backed eval exists to re-run.
- `tests/core/test_languages.py` inside the Docker image — not run there (path lookup cannot work in `/app`); it passed in both local suites.

### Rollback

- `git revert <sha>` then `uv pip install -r apps/api/requirements.txt -r apps/api/requirements-ai.txt` to restore the previous resolution.

### Harness-Delta

- backlog — `make test-docker` cannot pass as written: `.dockerignore` copies `apps/api/.env` into the image (~59 dashboard/key tests redden) and `tests/core/test_languages.py` needs the repo root four levels up. Both pre-date this change.
- backlog — `specs/gh-193-booking-revise-idempotency/PLAN.md` is still `status: active` although PR #203 merged 2026-09-15; the lane hooks bind to it for any commit that does not stage its own SUMMARY.
