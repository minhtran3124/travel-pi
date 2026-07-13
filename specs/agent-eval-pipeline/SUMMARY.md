# agent-eval-pipeline — Summary

Lane: high-risk
Confidence: high
Reason: Upgraded from normal — the work ships dependency manifests (`apps/api/evalkit/pyproject.toml`, an `agentevals` pin in `requirements-ai.txt`), which the canonical gate list treats as the detectable `external-provider` hard gate; no actual external service is introduced (see ESCALATIONS.md).
Flags: existing behavior, weak proof, external-provider (manifest-path gate)
Affects: apps/api/eval/ (offline eval harness), apps/api/evalkit/ (new portable package), apps/api/requirements-ai.txt
Input-type: new initiative

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- verbatim -->

> review current code changes and research evaluation pipeline for current project.
> I want to build the standard pipeline to evaluate the chatbot agent. Building the matrix, metrics, scripts, etc ...
> Help to ez mantain and scalable for testing/evaluation system when go to production

## What changed

Phase 1 shipped in 4 waves on `feat/agent-eval-pipeline`. A portable engine (`apps/api/evalkit/` — types, 5 ports, metric registry, dataset store, runner, CLI, report, baseline; installable standalone as `agent-evalkit`, pydantic-only core with `agentevals`/`deepeval` as extras) plus the travel-pi binding (`apps/api/eval/adapters/` — LangGraph runner, DB oracle, LLM extractor, taxonomy). 13 metrics across three families: judge-free deterministic, deterministic trajectory, and G-Eval judged (temp-0, k-repeat averaged). The golden matrix grew 24 → 84 cases across 10 capabilities × 5 scenarios, VN + EN, schema-validated at load. The six legacy eval modules were retired once each was confirmed superseded. `make eval-{smoke,full,baseline,compare}` + a CI workflow (keyless PR gate, judged nightly with baseline diff).

Three defects found and closed on the way: `no_hallucination` was blind (no `retrieval_context` — now fed from real tool outputs); seven goldens named metrics no rubric implemented (would have `KeyError`d mid-run after paid judge calls — rubrics recovered from the MIN-65 commit that defined them, and unknown metric names are now rejected at load); the `.deepeval/` runtime cache was untracked noise (gitignored).

### Rationale

Two user-accepted constraints drive the shape: (1) **portability** — the engine (`evalkit/`) is built framework-free with `typing.Protocol` ports from the first commit and an ast boundary test forbidding `app.*` imports, so extraction into a standalone package / MCP server later needs no rewrite; (2) **DB-as-Oracle** — because this backend is deterministic (MD5-seeded flights/hotels, DB-backed trips/FX), eval recomputes ground truth from the DB instead of asking a judge, wherever a fact is computable. Judged G-Eval (temp-0, k-repeats, per-capability binary pass rates) covers only subjective qualities and runs nightly; the PR gate is keyless/deterministic.

### Alternatives considered

- **Build inside `eval/` and "extract later"** — rejected: the extraction step never happens; the port boundary is cheaper to hold from day one than to retrofit.
- **Build the MCP server now** — rejected: nothing stable to expose until the Report JSON contract exists; MCP is a transport shell over the ports (phase 3).
- Confident AI cloud for baselines/regression — rejected: local-first, self-maintained.
- LangSmith for tracing — rejected: self-host requires Enterprise; Langfuse (MIT) is the phase-2 candidate.
- Judged eval on every PR — rejected: judge cost + variance.

### Deviations

- Rule 2 — Added `.deepeval/` to root `.gitignore` (generated cache/telemetry was untracked noise). Commit `ae766b9`.
- Rule 3 — `evalkit/pyproject.toml` needs explicit `packages`/`package-dir` (the manifest lives inside the package dir per the portable layout); verified with a throwaway editable install. Task 1.1.
- Rule 1 — Test fixture used `{"role": ...}` for a Trace message; changed to `{"type": ...}`, which is the shape LangChain actually serializes messages to (and it stops the `authorization` keyword gate false-positiving on the word `role`). Task 1.1.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| eval suite (all 4 waves) | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval -q` | 0 | 133 passed |
| boundary gate (portability) | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_boundary.py -q` | 0 | ast walk of `evalkit/`; fails on any `app.*`/fastapi/sqlalchemy/langgraph import |
| standalone installability | `pip install -e apps/api/evalkit` in a throwaway venv | 0 | imports with pydantic alone — the portability claim is tested, not asserted |
| full API suite (no regression) | `cd apps/api && DATABASE_URL="sqlite:///./test_verify.db" OPENAI_API_KEY="" ../../.venv/bin/python -m pytest tests/ -q` | 1 | 1625 passed, **5 failed — all pre-existing** (`tests/core/test_config_llm.py`, `test_embeddings.py`, `tests/tools/test_routing_tools.py`: this checkout's `.env` ships real ORS/OpenAI keys). No file under those paths was touched. Without the DB override the run errors at setup (known: `.env` points at a Postgres that is not up). |
| suite auditability | `cd apps/api && ../../.venv/bin/python -m eval --suite full --dry-run` | 0 | 66 goldens listed with their metrics, no agent invoked; previously would have `KeyError`d on unregistered metric names |
| make targets | `cd apps/api && make -n eval-smoke eval-full eval-baseline eval-compare` | 0 | all four resolve |
| lint | `cd apps/api && ../../.venv/bin/ruff check evalkit eval && ../../.venv/bin/ruff format --check evalkit eval` | 0 | clean |

**Not yet run (be honest about it):** a real judged `make eval-full` against a live LLM + DB. It needs a reachable model (the eval graph bypasses `AgentConfigCache` and falls back to env `gpt-5`/`gpt-5-mini` → 403) and a seeded DB. Until that run happens there is **no baseline**, so `eval-compare` has nothing to gate against — that is the first thing to do next, not a claim this work already made.

### Rollback

- Revert the whole initiative: `git revert ae766b9..HEAD` on `feat/agent-eval-pipeline`, or simply drop the branch (`git branch -D feat/agent-eval-pipeline`) — nothing is merged to v3 and no app/agent code, schema, or migration is touched.
- Uninstall the local package if it was editable-installed: `pip uninstall agent-evalkit`.
- `apps/api/eval/` legacy modules are untouched until task 4.1; until then the existing harness keeps working.

### Harness-Delta

- backlog — the blast-radius hook corroborates every edit against a stale "active plan" (`specs/web-trip-planner/PLAN.md`) rather than the slug being executed, so it flagged all correctly-scoped files in this initiative. Worth a `/compound` entry: the hook needs to resolve the active plan from the current branch/slug.
- backlog — `risk-corroboration.sh` cannot distinguish "new external *service*" (Rule-4 STOP) from "new library pin / local package manifest" (Rule-3 auto-fix): any `pyproject.toml`/`requirements*.txt` in the diff trips `external-provider`. And `RISK_WARN_CATEGORIES` cannot be supplied by the agent (PreToolUse hooks read the Claude Code process env, not the command env), so the only in-band resolution is a lane upgrade.
