# review-b7-eval-baseline-ci — Design

Status: approved by the user in brainstorming (2026-09-07). Lane: high-risk. Decisions E001–E003 in `ESCALATIONS.md` are inputs, not re-opened here.

## Purpose

Give the agent eval a committed baseline and a working regression gate, on the evalkit branch (`feat/agent-eval-pipeline`) now that `main` has been merged into it (commit `1092ccf`). Deep-review item 7 ("Eval không có baseline, không gate CI") is the source.

## Constraints (from intake decisions)

- **E001** — work happens on the evalkit branch; the MIN-58 harness stays retired.
- **E002** — no judged (paid) eval on GitHub Actions: no `OPENAI_API_KEY` secret, no nightly cron. The regression gate is a **local ritual** (`make eval-check`), not a CI job.
- **E003** — the baseline is a committed Report JSON (`eval/baselines/main.json`) compared with the existing tolerance gate (`evalkit.baseline.compare`, tolerance 0.05, plus the masked-flip rule).
- No changes under `apps/api/app/**`. An agent bug surfaced by re-validation becomes a GitHub issue; the golden stays and the baseline records the failure.
- The baseline run is executed by the implementing agent, locally, against Docker Postgres with the real key in `apps/api/.env`, **after** goldens are re-validated (user-authorised spend: ~84 agent turns + ~105 judge calls at k=3).

## Chosen approach — A: finish evalkit as it stands

Keep the ports/registry/report architecture (the portability decision of `specs/agent-eval-pipeline/` is not re-opened). Add only what is missing; every schema change is additive. Rejected: B (fold evalkit into `eval/`, drop ports — reverses a settled decision for no gain on this spec's goal) and C (baseline only, no port/re-validate — would freeze stale goldens and drop main's 16 legacy cases; rejected by the user at scope).

## Components

| # | File | Change |
| --- | --- | --- |
| 1 | `apps/api/eval/__main__.py` | `--dry-run` no longer constructs `LangGraphRunner` (which calls `build_graph` → eager `get_agent_llm` → OpenAI client needs a key). Pass a no-op runner; dry-run must exit 0 with no key in the environment. |
| 2 | `.github/workflows/eval.yml` | Delete the `eval-nightly` job, the `schedule:` trigger and every `secrets.*` reference. Keep `eval-smoke` (`pytest tests/eval` + keyless dry-run) on the same PR path filter. Keep `workflow_dispatch` only if it still has a job to run (it does: eval-smoke). |
| 3 | `apps/api/evalkit/types.py` | `Golden.expected_tasks: list[str] \| None = None` (additive). |
| 4 | `apps/api/eval/adapters/langgraph_runner.py` | After `graph.invoke`, set `Trace.meta["tasks"] = [t["agent"] for t in out.get("tasks") or []]` and `Trace.meta["suggestions"] = suggestions_for_flow(out.get("current_flow"), trip_facts=out.get("trip_facts"))` (profile omitted — the eval store is empty). `Trace` schema unchanged; `meta` is the open extension point. |
| 5 | `apps/api/evalkit/metrics/deterministic.py` | New registered metric `tasks_expected`: `set(golden.expected_tasks) == set(trace.meta.get("tasks"))`. Order-independent because tasks fan out in parallel (`gh-117`). `not_applicable` when the golden has no `expected_tasks`. |
| 6 | `apps/api/evalkit/metrics/judged.py` | `build_retrieval_context` appends one line per key in `trace.meta.get("suggestions", [])` so the `suggestion_relevance` rubric finally sees what it was written for (closes the "Known gap" in the module docstring). |
| 7 | `apps/api/eval/adapters/config.py` | Add capability `suggestions` (default threshold 0.7). |
| 8 | `apps/api/eval/datasets/routing.json` | +6 goldens (legacy cases have no `id`; assign `routing-multi-{en,vi}-NN` following the existing scheme) ported from main's legacy `multi_intent.json` (recover from `main@4e032c7`). Cases with an empty `expected_plan` keep `expected_flow` + `flow_match`; cases with follow-ons get `expected_tasks = [expected] + expected_plan` and metric `tasks_expected` (no `flow_match`: a multi-intent turn ends with `current_flow == "synthesize"`). |
| 9 | `apps/api/eval/datasets/suggestions.json` | New file: 10 goldens ported from main's legacy `suggestions.json` (that file holds 10 cases, not the 12 the intake note said), capability `suggestions`, scenario `happy`, suite `full`, metrics `[flow_match, suggestion_relevance]`, ids `suggestions-happy-{en,vi}-NN`. |
| 10 | `apps/api/eval/baselines/main.json` | Committed baseline from a `--suite full --repeat 3` run on the merged branch, after re-validation. |
| 11 | `apps/api/Makefile` | `eval-check` = `eval-full` then `eval-compare`. `eval-compare` prints an actionable message when the baseline file is missing instead of a traceback. |
| 12 | `apps/api/eval/README.md` | Document the local gate ritual and its cost (~84 agent turns + ~105 judge calls per `eval-check`, which is why it is local — E002), the no-CI decision, the `tasks_expected` metric and `expected_tasks` field, and how to refresh the baseline. |
| 13 | `apps/api/evalkit/pyproject.toml` + `apps/api/evalkit/README.md` | Delete the manifest (standalone install is unused; nothing imports or tests it) and remove the README's "Optional extras" section that quotes it. `tests/eval/test_boundary.py` stays. |

## Data flow

1. `python -m eval --suite full --repeat 3 --out eval/reports/latest.json` → `JsonDatasetStore` loads all `eval/datasets/*.json` (now 102 goldens = 86 + 6 + 10 in the store; `--suite full` is an exact-match filter so a full run covers the 84 full-suite goldens and the baseline records those 84, validated against `Golden` + taxonomy + registered metric names) → `LangGraphRunner.run(golden)` per case → `Trace` (reply, tool calls, flow, messages, **meta{tasks, suggestions}**) → metrics → `Report`.
2. Re-validation triage per failing case: (a) golden stale vs. current main behaviour (e.g. supervisor v10 routing, renamed tools) → fix the golden here; (b) agent defect → open a GitHub issue, keep the golden, let the baseline record the fail. Re-run until every remaining failure is class (b).
3. `make eval-baseline` copies `latest.json` → `eval/baselines/main.json`; commit.
4. Gate: `make eval-check` → fresh full run → `compare(report, baseline)` → exit 1 on a capability drop beyond tolerance or a masked flip.

## Error behaviour

- Dry-run with no key: exit 0, lists goldens. Real run with no key: unchanged (judged metrics skipped and logged; deterministic ones still run).
- `eval-compare` with no baseline: clear message naming `make eval-baseline`, exit 1.
- `tasks_expected` when the golden declares `expected_tasks` but the trace carries no `meta["tasks"]`: **fail** with detail — never a silent pass.
- `suggestion_relevance` when the trace has no suggestions: runs as today (tool-output context only); the detail says so.
- Pre-flight before the paid run: the live `agent_config` row `synthesize` has a NULL model. xia2 must confirm what `get_agent_llm("synthesize")` resolves to in that case (env default vs 403) before the baseline run is attempted. If it resolves to an uncallable model, the fix is to set the row through the config dashboard or the seed CLI (data, not `app/**`), then re-run.
- `tasks_expected` grading assumes `state["tasks"]` always contains the primary agent (`tasks = [target] + follow-ons`, `app/agents/supervisor.py`). xia2 confirms single-intent turns populate it the same way, so the two no-follow-on goldens and the four with follow-ons are graded consistently.

## Tests

- Unit (`tests/eval/`): `tasks_expected` match / unordered / missing-meta fail / not_applicable; runner populates `meta.tasks` and `meta.suggestions` with a FakeLLM-scripted multi-intent supervisor; `build_retrieval_context` includes suggestion keys; dry-run keyless via subprocess with `OPENAI_API_KEY` set to the empty string (not unset — dotenv would refill it); dataset store loads exactly 102 goldens (86 existing + 6 multi-intent + 10 suggestions), `suggestions` capability non-empty; `make -n eval-check` resolves.
- Success criteria: **SC-1** `OPENAI_API_KEY= python -m eval --suite smoke --dry-run` exits 0 (empty value, not `env -u`: an unset var loses to `apps/api/.env`, see memory `env-u-does-not-neutralize-dotenv-secrets`). **SC-2** `eval.yml` contains no `schedule:` and no `secrets.` anywhere, comments included (line 74 today mentions the secret in a comment). **SC-3** `eval/baselines/main.json` is committed with `run_meta.suite == "full"`, `run_meta.repeat == 3` and 84 cases. **SC-4** `make eval-compare` against its own baseline exits 0; against a report with one capability's pass rate lowered by >0.05 exits 1. **SC-5** `pytest tests/eval` and the full BE suite pass.

## Out of scope

Judged eval on CI (E002), any `apps/api/app/**` change, Langfuse/LangSmith online eval, evalkit extraction/MCP, model-tier benchmarking.
