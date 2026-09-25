---
slug: llm-pricing-coverage
status: active
owner: Minh Tran
created: 2026-09-25
---

# LLM pricing coverage: stop unpriced models from silently dropping cost

## 1. Motivation

`estimate_cost` returns `None` for the whole run when any model in `by_model` is missing from
`MODEL_PRICES_USD_PER_1M` (`apps/api/app/core/pricing.py:53-65`). That is the right choice
(no fake `0.0`), but the `None` is silent. `AgentRunRepository.totals()` then skips NULL-cost rows
(`app/repositories/agent_run.py:169-185`), so spend is under-counted with no signal. Existing tests
already cover the static catalogue and the env defaults (`tests/core/test_pricing.py:95-106`).
They do not cover a model that arrives at runtime through a DB `agent_config` row
(dashboard or `seed_agent_config --model`).

This slice is the prerequisite for `llm-spend-caps`: a dollar budget summed over `cost_usd` is
only as good as the price coverage. It implements items 5 and 6 of
`specs/llm-gateway-eval/research-brief.md` §4.

## 2. Non-goals

- Rejecting an unpriced model in the config dashboard. That is a public-contract change, and
  intake chose a warning instead.
- Fetching prices from a live API, or changing any price value.
- Pricing background LLM work (memory extraction). The report only surfaces those tokens as
  unpriced.
- Any budget enforcement. That belongs to `llm-spend-caps`.

## Global Constraints

- ORM access stays in `app/repositories/`. The script calls a repository method, following the
  pattern in `scripts/cache_hit_report.py`.
- The warning is logged once per normalized model name per process, so a hot path cannot flood
  the logs. Use `logging.getLogger(__name__)`, as in `app/core/agent_config_cache.py:11`.
- `estimate_cost` keeps its contract: it returns `None` on an unpriced model and never `0.0`.
  The existing tests in `tests/core/test_pricing.py` must still pass unchanged.
- Keep comments minimal: no `:param` blocks, and one-line docstrings in the style of `pricing.py`.
- Put one parameter per line, with a trailing comma, in any multi-parameter signature.
- Run tests from `apps/api/` with `../../.venv/bin/python -m pytest`. Do not pass
  `OPENAI_API_KEY=` empty.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | Costing a run with an unpriced model logs one WARNING that names the model, even if costed twice. The result is still `None`. | `cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_pricing.py -q` | exit 0 |
| SC-2 | Loading agent_config rows whose model is unpriced logs a WARNING naming the agent and the model. Priced rows log nothing. | `cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_agent_config_cache.py -q` | exit 0 |
| SC-3 | `python -m scripts.cost_report --since 30d` prints each month's priced cost, the count and tokens of NULL-cost runs with their unpriced models, and the unpriced background tokens. | `cd apps/api && ../../.venv/bin/python -m pytest tests/scripts/test_cost_report.py -q` | exit 0 |
| SC-4 | The new and changed code passes lint | `cd apps/api && ruff check app scripts` | exit 0 |

## 4. Tasks

### Task 1.1 — Warn once per unpriced model in estimate_cost, and add is_priced (wave 1)

- **Files:** apps/api/app/core/pricing.py, apps/api/tests/core/test_pricing.py
- **Action:** Add `is_priced(model: str) -> bool`, which checks `normalize_model(model)` against
  the table. In `estimate_cost`, when a model has no price, log
  `logger.warning("[pricing] unpriced model %r — run cost recorded as NULL", normalized)` once per
  normalized name per process (a module-level `set`), then return `None` as today. Add tests:
  one warning across two calls with the same unpriced model (use `caplog`, and clear the dedup
  set in a fixture), no warning for a priced model, and `is_priced` true for a dated snapshot and
  false for an unknown name.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_pricing.py -q`
- **Done:** New tests pass, and every pre-existing test in the file passes unchanged.
- **Criteria:** SC-1, SC-4
- **Interfaces:** Consumes: the existing price table and normalize_model. Produces: `app/core/pricing.py::is_priced`.

### Task 1.2 — Monthly cost-coverage report script (wave 1)

- **Files:** apps/api/app/repositories/agent_run.py, apps/api/scripts/cost_report.py, apps/api/tests/scripts/test_cost_report.py
- **Action:** Add `AgentRunRepository.cost_rows_since(since: datetime)`. It returns
  `created_at, input_tokens, output_tokens, cost_usd, by_model, background_tokens` for runs at or
  after *since*, using the same ISO string cutoff as `totals()`. Add `scripts/cost_report.py`,
  modelled on `scripts/cache_hit_report.py`: module docstring with usage and exit codes, and
  `--since Nd/Nh` (default `30d`). It must contain a pure `build_report(rows)` that groups by
  month (`created_at[:7]`) into: `runs`, `priced_cost_usd`, `unpriced_runs`, `unpriced_tokens`,
  `unpriced_models` (sorted model names from `by_model` of NULL-cost rows), and
  `background_tokens`. The output is a fixed-width table plus a footer line telling the operator
  to compare `priced_cost_usd` with the provider invoice for the same month. Exit 0 when it ran,
  2 on a usage error, 3 when there are no runs in the window. Write tests on a tmp SQLite DB, as
  in `tests/scripts/test_cache_hit_report.py`: rows split by month, a NULL-cost row counted as
  unpriced with its model listed, and exit 3 on an empty window.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/scripts/test_cost_report.py -q`
- **Done:** Script tests pass, and `python -m scripts.cost_report --help` exits 0.
- **Criteria:** SC-3, SC-4
- **Interfaces:** Consumes: existing agent_runs columns. Produces: `app/repositories/agent_run.py::cost_rows_since`, `scripts/cost_report.py`.

### Task 2.1 — Warn when agent_config loads an unpriced model (wave 2)

- **Files:** apps/api/app/core/agent_config_cache.py, apps/api/tests/core/test_agent_config_cache.py
- **Action:** In `reload_from_db`, after building `cache`, log
  `logger.warning("[AgentConfigCache] agent %r uses unpriced model %r — its cost will be NULL", name, model)`
  for each row whose `model` is set and where `is_priced(model)` is false. Do nothing when
  `model` is None, because the node then falls back to the env default, which
  `test_config_defaults_are_priced` already covers. The warning must never raise. Add tests with
  one priced row and one unpriced row, using `caplog` and the existing test DB fixture pattern.
  If `tests/core/test_agent_config_cache.py` does not exist, create it, and name in the SUMMARY
  the paths you searched.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_agent_config_cache.py -q`
- **Done:** The test passes, and the unpriced row's warning names both the agent and the model.
- **Criteria:** SC-2, SC-4
- **Interfaces:** Consumes: `app/core/pricing.py::is_priced` (Task 1.1). Produces: `app/core/agent_config_cache.py::reload_from_db` unpriced-model warning.

## 5. Risks

- **Log noise.** A misconfigured model would warn on every call. Mitigation: dedup per process
  in `estimate_cost`. `reload_from_db` runs only when the config changes (a poll plus
  `updated_at` check), so it is naturally rare.
- **Test pollution.** The module-level dedup set is shared across tests. Mitigation: a fixture
  that clears it.
- **Report blind spot.** Some LLM calls may bypass the metrics callback entirely (eval,
  deepagents internals), so no report can show them. The footer's invoice comparison exists
  for exactly that delta.

## 6. Status Log

- 2026-09-25: plan written after intake (normal / medium). Worktree
  `../travel-pi-llm-pricing-coverage`, branch `feat/llm-pricing-coverage`. Baseline suite: 3129
  passed, 9 skipped.
