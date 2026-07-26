# gh-112 eval A/B — reflection ON vs OFF

Both arms run back to back on the same commit, same DB, same datasets, same judge. Arm A is the
baseline already posted; arm B flips only the context the harness hands the graph, which is exactly
the behavior the graph will have once the reflection node is removed.

| Field | Value |
|---|---|
| Commit | `42ab13c` (branch `fix/gh-109-clarification-restream`) |
| Arm A | `AgentContext()` → `allow_reflection=True`, `max_revisions=1` |
| Arm B | `AgentContext(allow_reflection=False)` (patched onto `eval.harness.AgentContext`) |
| Model, every node | `gpt-5.4-mini` (DB `agent_config` after `reload_from_db`) |
| Judge | `gpt-4o-mini`, threshold 0.70 |
| Cases | 37 loaded, 34 scored — the same 3 HITL cases skipped (empty reply) in both arms |
| Exit code | 0 / 0 |

## Results

| Metric | N | A: reflection ON | B: reflection OFF | Δ |
|---|---|---|---|---|
| Response Language | 10 | 1.00 / 100% | 1.00 / 100% | — |
| Search vs Booking Intent | 5 | 0.89 / 80% | **0.97 / 100%** | +0.08, +1 case |
| Format Quality | 4 | 0.89 / 100% | 0.88 / 100% | −0.01, pass rate unchanged |
| Memory Recall | 8 | 0.84 / 87.5% | 0.84 / 87.5% | — (same case fails in both) |
| Tool Correctness | 4 | 1.00 / 100% | 1.00 / 100% | — |
| Suggestion Relevance (GEval) | 8 | 0.64 / 50% | 0.75 / 62.5% | +0.11, +1 case |
| suggestion_relevance (deterministic) | 8 | 8/8 (100%) | 8/8 (100%) | — |
| no_hallucination | 0 | skipped | skipped | — |

### Failing cases per arm

| Metric | A (ON) | B (OFF) |
|---|---|---|
| Search vs Booking Intent | `Cho tôi xem các chuyến bay từ TP.HCM đi Tokyo` | none |
| Memory Recall | `Turn 1: Ngân sách của tôi khoảng 20 triệu…` | same case |
| Suggestion Relevance | Bangkok weather · `Add a note: …beach on day 2` · Phú Quốc budget · Tokyo expenses | Bangkok weather · Phú Quốc budget · Tokyo expenses |

## Verdict

**No regression on any rubric with reflection off.** Two rubrics nominally improved; the rest are
identical, and the single "decline" (Format Quality, −0.01 average) did not move a single case across
the threshold.

This does **not** prove reflection is actively harmful — it removes the objection that removing it
costs answer quality, which was the open question in the issue.

## Caveats — do not over-read these numbers

- **N is tiny** (4–10 cases per rubric). One case flipping is worth 10–25 percentage points of pass
  rate. Both nominal improvements are exactly one case each, so they are within single-case noise.
- **One run per arm, real LLM, non-deterministic.** Replies differ between runs regardless of the
  reflection setting. A tighter read would need several runs per arm.
- **Both arms hit a tool-error defect — deterministic, not flaky** (filed as #113). Replies claiming a
  "temporary trip lookup error" / "temporary issue" appear 4× in arm A and 2× in arm B. Root cause:
  these cases carry `trip_id=None`, so `get_trip_budget` (args come from `InjectedState`) is invoked
  with empty kwargs, and the sub-agent catch-all handler
  (`app/agents/subagents/_base.py:_tool_error_to_message`) labels **every** tool failure a temporary
  upstream outage. The affected cases are the same budget/expenses cases that fail Suggestion
  Relevance in both arms, so part of that rubric's failure count is this defect, not suggestion
  quality. The count differs between arms only because routing varies run to run.
- **Suggestion Relevance (GEval) remains the noise floor**: its deterministic twin passes 8/8 on the
  same replies in both arms.

## Reproduce arm B

Same setup as the baseline (see `gh-112-baseline-reflection-on.md` for the `.env` / `PYTHONPATH` /
`AgentConfigCache` gotchas), plus the context patch — `eval/harness.py` hardcodes `AgentContext()`
inside `_invoke_turn`, so patch the module-level name instead of editing repo source:

```python
import functools
import eval.harness as harness
from app.agents.context import AgentContext

harness.AgentContext = functools.partial(AgentContext, allow_reflection=False)
assert harness.AgentContext().allow_reflection is False
```
