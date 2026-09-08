# agent-eval-pipeline — Test Matrix

## Status values

| Status | Meaning |
| --- | --- |
| planned | Accepted as intended behavior, not implemented |
| in_progress | Actively being built |
| implemented | Implemented **and** proof exists |
| changed | Contract changed after earlier implementation |
| retired | No longer part of the contract |

## Matrix

| Behavior | Contract | Unit | Integration | E2E | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| evalkit stays portable | No module under `evalkit/` imports `app.*` / fastapi / sqlalchemy / langgraph | yes | — | — | implemented | `tests/eval/test_boundary.py` (ast walk); `pip install -e apps/api/evalkit` in a clean venv |
| Goldens are schema-valid | Every golden validates against `Golden` + the project taxonomy; unknown capability/scenario/metric fails at LOAD naming file + id | yes | — | — | implemented | `tests/eval/test_datasets.py::test_unknown_metric_raises_naming_file_case_and_metric`, `::test_real_dataset_metrics_are_all_registered` |
| Deterministic checks (judge-free) | flow, tool set, language, non-empty, arg shape — no LLM, no network | yes | — | — | implemented | `tests/eval/test_metrics_deterministic.py` (24 tests) |
| Trajectory checking | Tool-call order/membership vs `expected_trajectory`; subset default (extra calls allowed) | yes | — | — | implemented | `tests/eval/test_trajectory.py` (10 tests) |
| Judged metrics are variance-controlled | G-Eval at temperature 0, k-repeat averaged; rubrics are swappable data | yes | — | — | implemented | `tests/eval/test_metrics_judged.py` |
| Judged metrics never fake a pass | With no judge key: metric is skipped and recorded in `run_meta.skipped_judged_metrics` — never reported as passed | yes | — | — | implemented | `tests/eval/test_runner.py` |
| A crashed case is a FAILED case | An agent exception becomes a failed CaseResult, never a dropped one (dropping inflates pass rate) | yes | — | — | implemented | `tests/eval/test_runner.py` |
| Trace captures tool I/O | Each tool call paired with its output by `tool_call_id`; ordered messages preserved | yes | yes | — | implemented | `tests/eval/test_langgraph_runner.py` (FakeLLM, 8 tests) |
| no_hallucination is grounded | Judge receives `retrieval_context` assembled from real tool outputs | yes | — | — | implemented | `tests/eval/test_metrics_judged.py` (retrieval_context assembly) |
| DB oracle recomputes truth | Oracle calls the same FlightService / HotelService / CurrencyService / TripService the agent's tools call — no re-derived seed math | yes | yes | — | implemented | `tests/eval/test_db_oracle.py::test_flight_offers_recomputes_the_real_seeded_price_range` (seeded DB) |
| Oracle catches a hallucination | A reply claiming a wrong price FAILS, with both the real and claimed values in the detail | yes | yes | — | implemented | `tests/eval/test_db_oracle.py::test_fails_and_catches_a_hallucinated_wrong_price` |
| LLM never adjudicates | The extractor only parses the value the reply states; code compares and code decides | yes | — | — | implemented | `tests/eval/test_extractor.py`; `evalkit/metrics/oracle.py` |
| Extractor/oracle stay in sync | Extracted field names are pinned against `DbOracle.lookup()` keys — a rename on either side fails loudly instead of looking like a hallucination | yes | yes | — | implemented | `tests/eval/test_extractor.py::test_schema_field_names_line_up_with_dboracle_lookup_keys` |
| Per-capability regression gate | A capability below threshold, or a pass→fail flip inside a capability that also lost rate, exits non-zero | yes | — | — | implemented | `tests/eval/test_baseline.py` (14 tests) |
| Suite is auditable before it runs | `--dry-run` lists every selected golden + its metrics without invoking the agent | yes | — | yes | implemented | `python -m eval --suite full --dry-run` → 66 goldens, exit 0 |
| PR gate is honest | CI PR job runs only what it can prove keylessly (offline suite + dry-run); it does not claim to have run the agent | — | — | yes | implemented | `.github/workflows/eval.yml` (documented in-file) |
| Judged nightly run + baseline diff | Nightly runs the judged matrix and diffs it against `eval/baselines/main.json` | — | — | no | **planned** | Needs the `OPENAI_API_KEY` repo secret **and** a first committed baseline — neither exists yet |
| A real judged full run | `make eval-full` against a live LLM + seeded DB produces a Report | — | — | no | **planned** | Not yet run: needs a reachable model (eval bypasses `AgentConfigCache` → env `gpt-5` → 403) and a DB |

## Evidence rules

- A row is `implemented` only when a re-runnable artifact exists. The two `planned` rows at the bottom are the honest gap: the machinery is built and unit-proven, but no judged run has executed against a live model, so **there is no baseline yet and nothing for `eval-compare` to gate against**. That is the next action, not a completed claim.
