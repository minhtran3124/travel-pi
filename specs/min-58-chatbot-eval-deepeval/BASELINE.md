# MIN-58 Eval Baseline

First real keyed run of the DeepEval harness (ticket step 4). Recorded 2026-07-06.

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
