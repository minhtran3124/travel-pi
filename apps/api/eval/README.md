# Chatbot Evaluation (`eval/`)

Offline quality checks for the Travel Assistant agent (MIN-58).

## Idea

Test **what the agent says**, not just that code runs. Each case sends a real message
through the LangGraph agent, then scores the reply against natural-language rubrics using
an **LLM-as-judge** (DeepEval's `GEval`) plus a deterministic tool check. This catches
regressions that unit tests can't — wrong language, wrong intent, hallucinated facts,
messy formatting.

Two layers live side by side:

| Layer | File | Judge | Needs a key? | Purpose |
|---|---|---|---|---|
| **Routing smoke** | `run_eval.py` + `metrics.py` | none (exact match) | no (FakeLLM in CI) | fast, free check that the supervisor routes to the right sub-agent |
| **Quality eval** | `run_deepeval.py` + `metrics_geval.py` | OpenAI `gpt-4o-mini` | **yes** | LLM-judged response quality (language / intent / grounding / format) + tool correctness |

## Structure

```
eval/
├─ run_deepeval.py    # keyed runner: agent → LLMTestCase → DeepEval evaluate()
├─ metrics_geval.py   # 4 G-Eval rubrics + ToolCorrectnessMetric; judge = gpt-4o-mini
├─ harness.py         # run_case(): drives the graph, builds one DeepEval LLMTestCase
├─ loader.py          # loads + validates datasets/*.json
├─ run_eval.py        # legacy no-network routing-accuracy smoke (unchanged)
├─ metrics.py         # routing_accuracy() helper for the smoke
└─ datasets/
   ├─ intent.json     # MIN-51 — search must not push booking
   ├─ language.json   # MIN-57 — reply in the user's language (EN + VI cases)
   ├─ tools.json      # MIN-46 — correct tool called (expected_tools)
   ├─ format.json     # MIN-54 — bold key info, tidy structure
   └─ routing.json    # supervisor routing (used by run_eval.py only)
```

The four G-Eval rubrics (registry `GEVAL_METRICS` in `metrics_geval.py`):
`response_language`, `search_vs_booking`, `no_hallucination`, `format_quality`.

## Setup

`deepeval` is already pinned in `requirements-ai.txt`. From the repo root:

```bash
uv pip install -r apps/api/requirements-ai.txt   # if not installed yet
export OPENAI_API_KEY=sk-...                      # a REAL key — the judge calls OpenAI
```

> The repo ships a fake `OPENAI_API_KEY=test` in `apps/api/.env`. The runner treats
> `test`/`placeholder`/empty (case-insensitive) as "no key" and **skips** — so set a real
> key in your shell to actually run the judge.

## Run

All commands from `apps/api/`:

```bash
# Quality eval (needs a real key; skips cleanly without one)
../../.venv/bin/python -m eval.run_deepeval

# Routing smoke (needs a provider key)
../../.venv/bin/python eval/run_eval.py

# Unit tests for the harness itself (no network, no key)
../../.venv/bin/python -m pytest tests/eval -q
```

`run_deepeval` builds the agent once and runs every dataset case through it, then:
applies the four G-Eval rubrics to every reply; applies `ToolCorrectnessMetric` **only** to
cases that declare `expected_tools`; **skips** cases with an empty reply (e.g. a HITL
plan-approval interrupt — GEval rejects an empty `actual_output`); and prints a per-metric
pass/fail table with the judge's reasoning.

## Add a test case

Append to the relevant `datasets/*.json`. Only `input` is required:

```json
{
  "input": "Tìm khách sạn ở Huế cuối tuần này",
  "expected_flow": "concierge",
  "expected_tools": ["search_hotels"],
  "metrics": ["search_vs_booking", "response_language"]
}
```

| Field | Meaning |
|---|---|
| `input` *(required)* | the user's message sent to the agent |
| `expected_flow` | which sub-agent should handle it (`concierge` / `booking` / `planner` / …) |
| `expected_tools` | tool names `ToolCorrectnessMetric` grades against (must be real, e.g. `search_hotels`, `get_weather`) |
| `metrics` | which rubrics are *relevant* — documents intent. **Note:** the runner currently applies all rubrics to all cases; this field is the basis for future per-case filtering |

Keep non-English inputs (e.g. Vietnamese) in `language.json` — they are what make
`response_language` able to catch the MIN-57 "answers in the wrong language" regression.

## Add a rubric (G-Eval metric)

In `metrics_geval.py`, write a factory returning a `GEval(name, criteria, evaluation_params,
threshold, model=JUDGE_MODEL)` and register it in `GEVAL_METRICS`. `criteria` is plain
English — describe what a good answer does and what to penalize; DeepEval derives the
grading steps from it.

## Notes / gotchas

- **DeepEval 4.x:** the param enum is `SingleTurnParams` (not `LLMTestCaseParams`).
  Constructing a `GEval(model=...)` eagerly requires `OPENAI_API_KEY` *present* (a
  key-presence check, not a network call) — so metrics are built only after the key guard.
- **Cost & non-determinism:** each keyed run makes real OpenAI calls and scores are
  LLM-judged (not perfectly reproducible). Run deliberately; it is **not** wired into CI.
- **Idea reference:** the runtime self-correcting variant (a grader sub-agent that revises
  the answer in-loop, à la LangChain's RubricMiddleware) is **out of scope here** — tracked
  as **MIN-59**.
```
