# agent-eval-pipeline — Research Brief

Date: 2026-07-13 · Sources: repo deep-dive (apps/api/eval/), uncommitted-changes review, external best-practices research (DeepEval 4.x docs, agentevals, Langfuse, industry guides).

## 1. What exists today (v3)

Two complementary layers in `apps/api/eval/`:

| Layer | Entry | Mechanism | Network |
|---|---|---|---|
| Routing smoke | `run_eval.py` + `metrics.py` | exact-match supervisor routing accuracy, threshold 0.9 | none (FakeLLM) |
| Quality eval | `run_deepeval.py` + `harness.py` + `metrics_geval.py` + `loader.py` | `harness.run_case()` invokes the real compiled LangGraph graph (MemorySaver + InMemoryStore), builds DeepEval `LLMTestCase`, per-case metric filtering via the case's `metrics` field | real judge (`gpt-4o-mini`, threshold 0.7) + real agent LLM |

**Datasets** (`eval/datasets/`, 24 cases): `intent.json` (6, search-vs-booking EN/VI), `language.json` (5, reply-in-user-language), `tools.json` (4, tool correctness), `format.json` (4, formatting), `routing.json` (5, supervisor routing only).

**Metrics**: G-Eval rubrics `response_language`, `search_vs_booking`, `format_quality`; `no_hallucination` defined but **non-functional** (no `retrieval_context` wired). Deterministic: `ToolCorrectnessMetric`, `routing_accuracy`.

**Unit tests**: `pytest tests/eval` (5 files, no network) guard the harness itself.

**Known gotchas** (confirmed): `build_eval_graph()` bypasses `AgentConfigCache`/DB config → env-default model 403s (run in docker w/ model override); PGVector double-build race (fixed by RLock, PR #82).

## 2. Gaps vs production-standard

1. **No CI integration** — `.github/workflows/ci.yml` runs only `pytest tests/`; no Makefile eval target.
2. **No baseline / regression gating** — baselines are hand-written markdown (`specs/min-58*/BASELINE.md`); no programmatic diff, no fail-on-regression exit code.
3. **No capability × scenario matrix** — 24 cases skewed to happy-path; booking, budget, journal, memory, date-resolution, error-handling capabilities uncovered or thin.
4. **No dataset schema/versioning discipline** — free-form JSON, no validation, no tags (capability/scenario/language/suite).
5. **LLM-judge variance unmanaged** — single run, small N, no temp-0/repeat averaging; gate is per-metric mean, not per-capability pass rate.
6. **`no_hallucination` blind** — tool outputs not captured as retrieval_context.
7. **No trajectory eval** — only set-membership tool correctness; no order/args/graph-path checking.
8. **No prod observability** — no tracing, no online sampled judging, no cost tracking beyond DeepEval's `evaluationCost`.

## 3. External best practices (2025–2026 consensus)

4-layer pyramid, cheapest first:
- **L0 deterministic** (tool names/args, schema, language detect, flow match) — every PR, zero judge cost.
- **L1 single-turn judged** (G-Eval goldens) — smoke subset on PR (cached, `deepeval -c`), full nightly.
- **L2 trajectory/multi-turn** — [agentevals](https://github.com/langchain-ai/agentevals) (MIT, langchain-ai) graph-trajectory match: strict/unordered/subset modes before any LLM-judge trajectory.
- **L3 online** — trace 100% prod traffic, LLM-judge a sample, feed confirmed failures back into goldens (data flywheel). Self-hostable pick: **Langfuse** (MIT, Docker Compose, OTel, open-sourced judge + CI experiment action). LangSmith self-host = Enterprise only.

Judge reliability: temperature 0, k=3–5 repeats averaged, gate on **binary pass-rate per capability** (not mean score), paired comparison vs baseline. Baseline diffing is a Confident-AI cloud feature — self-hosted pattern is: persist per-case results JSON as artifact on base branch, paired-compare in CI.

Matrix design: rows = capabilities (flight, hotel, booking, budget, journal, memory/personalization, multilingual VN/EN, date resolution, error handling); columns = scenarios (happy / ambiguous / multi-turn / tool-failure / adversarial); 3–5 goldens per cell, grown from real prod failures, git-versioned with per-golden metadata tags — the MIN-58 per-case rubric filtering is already the recommended pattern.

## 4. Decision forks (need human input)

1. **Prod observability (L3)**: adopt self-hosted Langfuse (new external service — Rule 4 gate) vs defer. Recommendation: separate phase-2 spec, not in this plan.
2. **CI judge budget**: nightly full judged run needs a real `OPENAI_API_KEY` secret in GitHub Actions + spend. Recommendation: PR job stays keyless (L0 + FakeLLM routing); nightly judged job behind a repo secret, skip-if-absent.

## 5. Recommended scope for this initiative (phase 1, no new external services)

1. Golden schema (pydantic) + validated, tagged datasets restructured into the capability × scenario matrix (~60–80 goldens, seeded from the existing 24 + MIN-65 spec cases).
2. Deterministic metric layer (L0) + agentevals trajectory matching (L2-lite, dev dependency only).
3. Wire tool outputs as `retrieval_context` → activate `no_hallucination`.
4. Unified runner: `--suite smoke|full`, `--capability`, judge temp-0 + `--repeat k`, per-capability pass-rate report (JSON).
5. Baseline save/compare script with fail-on-regression exit code.
6. Makefile targets (`eval-smoke`, `eval-full`, `eval-baseline`) + CI: PR keyless job, nightly judged job.
7. README rewrite: how to add a golden / a metric / a capability (the maintainability contract).

Phase 2 (deferred, own spec): Langfuse tracing + online sampled judging + data flywheel.
