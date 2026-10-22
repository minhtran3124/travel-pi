# llm-pricing-coverage — Summary

Lane: normal
Confidence: medium
Reason: no hard gate; 2 flags (existing behavior — observability of cost, weak proof — prices are data); touches >1 file (pricing guard + a script + tests)
Flags: existing-behavior, weak-proof
Affects: app/core/pricing.py, app/agents/metrics.py (cost recording), new apps/api/scripts/ delta script
Input-type: spec slice
Route: using-git-worktrees → subagent-driven-development
Escalate: no

> Documented default (why medium): an unpriced model is surfaced as a WARNING log at graph build / agent_config load plus a unit test asserting every seeded agent_config model has a price row — NOT a dashboard save rejection (that would be a public-contract change → high-risk).
> Prerequisite for `llm-spend-caps`: `estimate_cost` returns `None` for the whole run if ANY model is unpriced (`app/core/pricing.py:53-65`), so a dollar budget summed over `cost_usd` would silently under-count.

### Intent

> make research for
> - https://www.langchain.com/blog/langsmith-llm-gateway-runtime-controls-for-production-agents
> - https://www.langchain.com/langsmith/llm-gateway
> - https://www.langchain.com/blog/how-we-made-coding-agent-spend-predictable
>
> làm 1 nghiên cứu đnahs gía để áp dụng vào project hiện tại

> ok, run /feature-intake cho nhung de xuat o trren

> (asked "Bắt đầu `llm-pricing-coverage` luôn nhé?") → "ok"

Source backlog: `specs/llm-gateway-eval/research-brief.md` §4 (7 items). This slice covers: items 5 (pricing-miss guard) and 6 (cost-vs-invoice delta script).

## What changed

An unpriced model no longer turns a run's cost into a silent NULL.
- `estimate_cost` logs a deduplicated WARNING naming every unpriced model in the run. A new helper, `is_priced`, is exposed for this check.
- An `agent_config` reload warns for each agent pinned to an unpriced model. It also warns when the env default `llm_model` or `fast_llm_model`, which un-pinned agents fall back to, is unpriced.
- A new script, `scripts/cost_report.py`, reports per month: the priced cost, the NULL-cost runs that actually have unpriced models (listed by name), and the unpriced background tokens. The month the window starts inside is marked as partial. Use it to reconcile against the provider invoice.
- Saving an unpriced model in the config dashboard still succeeds, and the list page now shows a warning banner naming the agent and the model (E001 = B).
- Run on the dev DB, it shows 180 runs and $2.92 priced in 2026-09, no unpriced runs, and 244k uncosted background tokens.

### Rationale

estimate_cost already refuses to fake 0.0; the gap is that the None is silent. A warning + seed-coverage test closes it without changing any contract; the delta script (read-only SUM over agent_runs by month) gives the invoice comparison the LangChain post recommends.

### Alternatives considered

- Reject unpriced models in the config dashboard — deferred: public-contract change.
- Fetch prices from a live API — rejected: no stable official pricing API; adds an external dependency.

### Deviations

- Rule 1: the cost report counted NULL-cost runs with no tokens as unpriced (8 false positives on the dev DB). Fixed in 6ff9c43a.
- Rule 1: five correctness-review findings scored 75 or higher. Fixed in 2116a435: priced models were listed as unpriced, only the first unpriced model was warned about, unpriced env-default models were not warned about, an overflowing `--since` produced a traceback, and the partial first month was unmarked.
- Rule 1: the dashboard warning checked the raw form value, so a model with padding spaces or a blank model was falsely warned. It now checks the stripped value, and the list page re-checks `is_priced` so a crafted link cannot render the banner. Both were found by the Task 3.1 reviews.
- Rule 2: the agent_config warning dedupes on (agent, model) rather than on model alone, so every affected agent is named. Changed in 6ff9c43a.

### Intent Findings

- E001 (drift): the unpriced-model warning reached only the backend log, not the dashboard. Escalated, and the owner chose B. Resolved by adding the dashboard banner (Task 3.1).
- Re-review observation, not fixed: a NULL-cost run whose models are all priced shows `unpriced_runs=1` with no model listed. This is the same root cause as the cost_report.py:54 advisory below.

### Advisory Findings

Correctness findings scored below 75. They are not fixed; they are recorded here for the human.
- cost_report.py:54, score 70. A NULL-cost run with `llm_calls > 0` but zero tokens (no usage_metadata) is not counted as unpriced, and a NULL cost caused by a metrics exception is not told apart from a pricing gap. Fix: select `llm_calls` and add a `cost_missing` bucket.
- agent_config_cache.py:168, score 40. The try block wraps the whole loop, and the key is added before the log call, so one raising row stops the warnings for the remaining agents.
- agent_config_cache.py:16, score 25. `_WARNED_UNPRICED` is never reset, including by `AgentConfigCache.clear()`, so re-pinning an agent to the same unpriced model in the same process does not warn again.
- agent_run.py:187, score 40. `cost_rows_since` loads every row with no SQL aggregation, and `created_at` has no index. Acceptable for a manual operator script.
- pricing.py:83, scored 0 (unmodified line). The cost can go negative if `cached_tokens > input_tokens`.
- Minor findings from the task reviews: some tests assert against the real price table rather than the `fake_table` fixture; the dedup-reset fixtures are opt-in, not autouse; `cost_rows_since` returns a bare `list`; and the zero-token test uses `SimpleNamespace` rather than a DB Row.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| unit: estimate_cost warns per unpriced model, is_priced | `cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_pricing.py -q` | 0 | 18 passed | SC-1 |
| unit: reload warns for pinned and env-default unpriced models | `cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_agent_config_cache.py -q` | 0 | 19 passed | SC-2 |
| unit: cost_report grouping, unpriced filter, exit codes, partial month | `cd apps/api && ../../.venv/bin/python -m pytest tests/scripts/test_cost_report.py -q` | 0 | 8 passed | SC-3 |
| lint | `cd apps/api && ruff check app scripts` | 0 | All checks passed | SC-4 |
| unit: dashboard save warns (non-blocking) on an unpriced model, escaped | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_dashboard.py -q` | 0 | 24 passed | SC-5 |

### Not auto-verified

- Full backend suite. It ran green once at baseline (3129 passed) and has not been re-run after the final commit. It is run at branch finish.
- Real-DB behaviour of `scripts.cost_report` (dev Postgres, `--since 90d`/`30d`, exit 0). This reached truth by a manual run but is not a re-runnable Verify row, because it needs the local `.env`.

### Rollback

- `git revert --no-edit 2faa5daa..1a10a582`. This is log, script and banner only, with no schema or data change, so a revert is complete.

### Harness-Delta

- none
