# MIN-58 Eval Baseline

Keyed runs of the DeepEval harness (ticket step 4).

- **Run 3 — `gpt-5.4-mini`, eval calibrated (2026-07-09):** the trustworthy baseline. A
  diagnosis of Runs 1–2 found the low `Search vs Booking` / `Tool Correctness` numbers were
  **eval artifacts, not agent bugs**. Three fixes landed (`fix/min-58-eval-calibration`):
  (A) the runner now scores each rubric only on cases that declare it (was: all 4 rubrics on
  all 18 cases — a category error); (B) `tools.json` expected `search_hotels` for two date-less
  info searches, but the MIN-51/MIN-46 split correctly routes those to `browse_hotels`;
  (C) the `search_vs_booking` rubric no longer conflates "no results found" with pushing
  booking. Use THIS run for comparisons.
- **Run 2 — `gpt-5.4-mini` (2026-07-09):** raw re-run on the closest-to-production model.
  ⚠️ Its "agent/prompt bug (MIN-51/MIN-46)" read-out was **overturned by the Run-3 diagnosis** —
  MIN-51/MIN-46 are correct; the harness was miscalibrated. Kept below for history.
- **Run 1 — `gpt-4o-mini` proxy (2026-07-06):** original baseline, kept below for history.

## Run 3 — agent `gpt-5.4-mini`, judge `gpt-4o-mini`, eval calibrated (2026-07-09)

Datasets after the calibration fix; per-case rubric scoring (correct denominators). DB:
Postgres dev (`api-db-1`) up. Numbers are LLM-judged → not deterministic.

| Metric (rubric → ticket) | Pass | % | vs Run 2 (fan-out /18) |
|---|---|---|---|
| Response Language (MIN-57) | 10/10 | **100%** | was 15/18 · 83% |
| Tool Correctness (MIN-46) | 3/4 | **75%** | was 2/4 · 50% — Fix B; 1 transient weather miss |
| Format Quality (MIN-54) | 3/4 | **75%** | was 13/18 · 72% |
| Search vs Booking Intent (MIN-51) | 3/5 | **60%** | was 8/18 · 44% |
| Fact Grounding | — | n/a | **unassigned** — see below |

**Read-out:**
- With correct denominators the agent looks far healthier than Runs 1–2 implied. **Response
  Language is a clean 10/10**; Tool Correctness rose to 3/4 once the dataset expected the right
  tool (`browse_hotels`). The remaining Tool miss is a transient weather case, not a wrong tool.
- `Search vs Booking` 3/5 is within LLM-judge noise (a diagnostic pass the same day scored 4/5);
  no case pushed booking on a search — the misses are the judge nitpicking result presentation.
- **`Fact Grounding` is intentionally unassigned.** The `no_hallucination` rubric only sees
  `INPUT` + `ACTUAL_OUTPUT` — not the tool results — so it cannot verify grounding and penalizes
  every concrete hotel/flight fact as "invented" (a run with it assigned scored a meaningless
  2/7). **Follow-up:** wire tool-result output into the test case as `retrieval_context` and add
  it to the rubric's `evaluation_params` before scoring this metric.

Reproduce:

```bash
cd apps/api
export OPENAI_API_KEY=sk-...            # real key (judge + agent)
export LLM_MODEL=gpt-5.4-mini FAST_LLM_MODEL=gpt-5.4-mini
../../.venv/bin/python -m eval.run_deepeval
```

---

## Run 2 — agent `gpt-5.4-mini`, judge `gpt-4o-mini` (2026-07-09)

Dataset: 19 cases; 18 scorable, 1 skipped (booking case `"Đặt phòng khách sạn đó giúp tôi"`
→ HITL plan-approval interrupt → empty reply). DB: Postgres dev (`api-db-1`) up.

| Metric (rubric → ticket) | Pass | % | Δ vs Run 1 |
|---|---|---|---|
| Response Language (MIN-57) | 15/18 | 83% | = |
| Fact Grounding | 13/18 | 72% | = |
| Format Quality (MIN-54) | 13/18 | 72% | +5pp |
| Search vs Booking Intent (MIN-51) | 8/18 | 44% | −6pp |
| Tool Correctness (MIN-46) | 2/4 | 50% | = |

**Read-out:** upgrading the agent model from the `gpt-4o-mini` proxy to `gpt-5.4-mini` left
the scores essentially flat (moves are within LLM-judge noise). This confirms the Run-1
conclusion: `Search vs Booking` (44%) and `Tool Correctness` (50%) are the concrete targets
for the MIN-51 / MIN-46 fixes, not something a bigger model resolves on its own.

Reproduce:

```bash
cd apps/api
export OPENAI_API_KEY=sk-...            # real key (judge + agent)
export LLM_MODEL=gpt-5.4-mini FAST_LLM_MODEL=gpt-5.4-mini
../../.venv/bin/python -m eval.run_deepeval
```

---

## Run 1 — agent `gpt-4o-mini` proxy, judge `gpt-4o-mini` (2026-07-06)

## Conditions (read before comparing future runs)

| | |
|---|---|
| **Agent under test** | `gpt-4o-mini` — the account's OpenAI project has **no access to the production `gpt-5`/`gpt-5-mini`** (403 `model_not_found`), so the agent was run on `gpt-4o-mini` via `LLM_MODEL`/`FAST_LLM_MODEL` override. **This baseline does NOT reflect the production model.** |
| **Judge** | `gpt-4o-mini` (DeepEval G-Eval LLM-as-judge) |
| **Dataset** | 19 cases; 18 scorable, 1 skipped (booking case `"Đặt phòng khách sạn đó giúp tôi"` → HITL plan-approval interrupt → empty reply) |
| **DB** | Postgres dev DB up (`api-db-1`) so agent tools resolve |
| **Reproducibility** | LLM-judged → **not deterministic**; numbers vary a few points run-to-run |

## Result

| Metric (rubric → ticket) | Pass | % |
|---|---|---|
| Response Language (MIN-57) | 15/18 | 83% |
| Fact Grounding | 13/18 | 72% |
| Format Quality (MIN-54) | 12/18 | 67% |
| Search vs Booking Intent (MIN-51) | 9/18 | 50% |
| Tool Correctness (MIN-46) | 2/4 | 50% |

*(Tool Correctness scored only on the 4 cases that declare `expected_tools`.)*

## Read-out

- **`Search vs Booking` (50%) and `Tool Correctness` (50%) are the weak spots** — the eval
  reproduces exactly the symptoms MIN-51 (search queries pushed toward booking) and MIN-46
  (wrong/missing tool calls) describe. The harness turns those bugs into measurable numbers,
  which is the point.
- `Response Language` (83%) is the strongest — bilingual EN/VI cases mostly get same-language
  replies; a few VN cases still slipped.
- Some agent replies degraded gracefully on transient tool errors (e.g. weather) — realistic,
  not a harness failure.

## Follow-ups

- Re-run on the production model once the OpenAI account is granted `gpt-5` access — this
  number is the gpt-4o-mini proxy, not the shipping baseline.
- The weak `Search vs Booking` / `Tool Correctness` scores are the concrete targets for the
  MIN-51 / MIN-46 fixes; re-run after each to measure the delta.

## Reproduce

```bash
cd apps/api
export OPENAI_API_KEY=sk-...            # a real key (judge + agent)
export LLM_MODEL=gpt-4o-mini FAST_LLM_MODEL=gpt-4o-mini   # until gpt-5 access
../../.venv/bin/python -m eval.run_deepeval
```
