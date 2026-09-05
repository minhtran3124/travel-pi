# agent-tool-round-budget — Summary

Lane: normal
Confidence: high
Reason: 3 flags (existing behavior, multi-domain, weak proof); no block-mode hard gate — the diff touches the shared sub-agent graph and a versioned prompt, not auth/schema/routes/providers.
Flags: existing-behavior, multi-domain, weak-proof
Affects: app/agents/subagents/_base.py (the ReAct topology all five specialists compile from), app/prompts/planner (new version), app/agents/prompt_map.py node list
Input-type: change request
Route: using-git-worktrees → writing-plans (>2 files, >3 steps) → subagent-driven-development
Escalate: no

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

cho việc gộp 2 hướng 1 + 2

(The two directions are options 1 and 2 from the investigation of the GraphRecursionError reported
by the user with a container-log screenshot, verbatim from that reply:

1. "Bỏ `trip_guard` khỏi đường đi khi `state["trip_id"]` đã có. Cho `tools_condition` route thẳng
   sang `tools`, chỉ rẽ vào guard khi thật sự cần chặn. Hàm điều kiện trên cạnh không tốn
   super-step. Ngân sách tăng 8 lên 12 vòng, sửa nhỏ, có test đo sẵn."
2. "Dạy planner gộp nhiều `add_itinerary_item` vào một lượt tool call. ToolNode chạy song song các
   call trong cùng một AIMessage nên cả lịch 6 ngày chỉ tốn 1 vòng. Sửa prompt, rủi ro thấp, nhưng
   phụ thuộc model có nghe hay không.")

## What changed

`assistant`→`tools` now routes directly when a call cannot need blocking (active trip, or no trip-scoped call), only detouring through `trip_guard` when it can genuinely fire — 3 super-steps/round drops to 2 on the fast path, raising the round ceiling from 8 to 12 under the unchanged `agent_recursion_limit=25`. Planner v12 adds one instruction: batch several `add_itinerary_item` calls into one response instead of one per turn. `trip_guard`'s blocking logic, `Command` shape, and node identity are unchanged.

### Findings at intake (evidence from the investigation)

- Sub-agent topology is `assistant → trip_guard → tools → assistant`
  (`app/agents/subagents/_base.py:255-264`), so **every** tool-calling round costs 3 super-steps.
  With `agent_recursion_limit = 25` (`app/core/config.py:177`) the ceiling is 8 rounds
  (`3N + 1 ≤ 25`).
- `trip_guard` is a pure no-op when a trip is active: `if not needing_trip or state.get("trip_id"):
  return Command(goto="tools")`. It burns a third of the budget to decide nothing.
- Observed failure: thread `conv=4753c53f…`, planner task `032ed25d-d199-9d5b-25dd-da7788abe501`,
  checkpoint steps −1..25 all inside one turn (04:32:40 → 04:32:53). 8 rounds ran
  (`recall_past_trips`, `search_places`, `add_itinerary_item` ×6), the 9th round's guard step
  exceeded the budget.
- The planner emits **one** call per round (`planner → tools (1 call(s))` on every line), so an
  itinerary costs one round per item.
- `tests/agents/test_plan_everything.py` already MEASURES this: a 7-tool chain streams 22 states
  against a limit of 25. The measurement exists but no test covers ≥9 rounds.
- Blast radius of the topology change: all five specialists compile from `build_subagent`
  (planner, concierge, journal, booking, budget). `app/agents/prompt_map.py:46` hardcodes
  `_SUBGRAPH_NODES = ("assistant", "tools", "trip_guard")`; `tests/agents/test_trip_guard.py`,
  `test_prompt_map.py`, `test_agent_config_coverage.py` reference the node.

### Rationale

Direction 1 is the structural fix (reclaims 8→12 rounds for every specialist, deterministic);
direction 2 is the behavioural fix (an itinerary collapses from N rounds to 1, but depends on the
model obeying prose). Shipping them together is what the user asked for, and they are
complementary: 1 raises the ceiling, 2 lowers the demand. Neither removes the guard's protection —
the no-trip path must still block, deterministically, exactly as GH-113 established.

### Alternatives considered

- Raise `agent_recursion_limit` only — pushes the wall back without removing the waste, and makes
  every genuinely-stuck loop run longer before failing. Rejected as direction 3 at investigation.
- Direction 2 alone — leaves the 8-round ceiling in place for every other multi-tool turn.
- Direction 1 alone — an itinerary of 12+ items still dies.

### Deviations

- Rule 1 — Task 1.1: implementer moved `InMemoryStore`'s import to module scope, touching a line inside the pre-existing test the brief said to keep unmodified (it was only used by that one test, not the new ones). Controller reverted the import to its original local scope before commit. `tests/agents/test_trip_guard.py`. Commit `759876a`.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| guard skipped when it cannot block | `.venv/bin/python -m pytest apps/api/tests/agents/test_trip_guard.py -q -k skips_guard` | 0 | run from repo root at 0f99ade | SC-1 |
| no-trip blocking path unchanged | `.venv/bin/python -m pytest apps/api/tests/agents/test_trip_guard.py -q` | 0 | 15 tests, includes 2 new | SC-2 |
| 10-round turn fits recursion budget | `.venv/bin/python -m pytest apps/api/tests/agents/test_trip_guard.py -q -k round_budget` | 0 | inline test tool, no DB | SC-3 |
| existing 7-tool-chain headroom golden | `.venv/bin/python -m pytest apps/api/tests/agents/test_plan_everything.py -q` | 0 | unmodified | SC-4 |
| planner v12 batching instruction | `.venv/bin/python -m pytest apps/api/tests/prompts/test_planner_prompt.py -q` | 0 | content-only, no version pin | SC-5 |
| static node-name coverage unaffected | `.venv/bin/python -m pytest apps/api/tests/agents/test_prompt_map.py apps/api/tests/agents/test_agent_config_coverage.py -q` | 0 | 27 tests | SC-6 |
| lint | `ruff check apps/api/app/agents/subagents/_base.py apps/api/app/prompts/planner apps/api/tests/agents/test_trip_guard.py apps/api/tests/prompts/test_planner_prompt.py` | 0 | | SC-7 |
| intake evidence | `grep -n "trip_guard" apps/api/app/agents/subagents/_base.py` | 0 | pre-change: guard was a node visited every round | |

### Advisory Findings (correctness review, below threshold or unmodified-line — not auto-fixed)

- **Retry-induced duplicate itinerary writes (score 50, Rule 1-3)** — the planner's `tools` node
  runs under `TRANSIENT_RETRY` (retries on `UpstreamError`); planner also binds weather/routing
  tools that re-raise bare `UpstreamError`. A batched round mixing an `add_itinerary_item` write
  with a call that then fails transiently causes LangGraph to retry the WHOLE node, re-executing
  already-committed writes (`add_itinerary_item` has no `idempotency_key` param). Pre-existing
  mechanism; v12's batching instruction raises how many writes one retry can duplicate (1 → N).
  Follow-up: pass an `idempotency_key` derived from the tool_call_id, or scope the retry policy
  away from non-idempotent writes. `app/tools/trip_tools.py`, `app/agents/retry.py`.
- **Batching may collaterally block `create_trip` (score 25, Rule 1-3)** — v12's new step-4
  sentence is not explicitly scoped to "once a trip exists"; if a compliant-but-imprecise model
  combines `create_trip` with `add_itinerary_item` in one response despite the pre-existing,
  more specific "No active trip yet" rule forbidding exactly that, `trip_guard` blocks the whole
  batch including `create_trip`. Scored low because the existing rule already forbids the
  triggering behavior; no evidence of it firing in practice. `app/prompts/planner/v12.md`.
- **SQLite lock under concurrent batched writes (score 25, Rule 1-3)** — batched `add_itinerary_item`
  calls open separate DB sessions/transactions concurrently; against local dev SQLite this could
  raise `database is locked`. Scored low: sqlite3's default busy timeout likely absorbs a brief
  single-INSERT lock, and Docker/prod run Postgres. `app/tools/trip_tools.py` (unmodified).
- **Introspection guard AttributeError (score 0, unmodified-line, pre-existing)** — `app/agents/subagents/_base.py:84`
  (`fn = tool.coroutine or tool.func`) sits outside its nearby try/except; a plain `BaseTool`
  subclass with neither attribute would crash `build_subagent` at startup. Entirely pre-existing,
  not triggered or made more likely by this diff.
- **Timestamp-format tiebreak assumes ISO strings from `_utc_now_iso()` (re-review P3, advisory)** —
  the new `created_at` tiebreak compares timestamp strings lexically; a row whose `created_at` was
  written in a different format (a legacy/manual/external insert) could sort out of true
  chronological order, though still deterministically. Not observed in any current write path
  (`grep -rn "TripItem(" app scripts tests` shows only the mixin default); legacy DB row content
  is unknown, not checked. `app/repositories/trip.py`.
- **Test measures 10 rounds, claim was "up to 12" (intent review, advisory)** — the round-budget
  test proves 10 sequential rounds fit; the arithmetic ceiling (`2N+1≤25`) is 12, but nothing pins
  12 specifically. `tests/agents/test_trip_guard.py`.

### Not auto-verified

- The user-visible symptom (a long itinerary turn completing instead of 500-ing) — reached
  traceability via container logs and the checkpoint table; a live replay is the real proof and
  needs `docker exec api-api-1 touch app/main.py` after any prompt change.

### Rollback

- n/a (no code change yet)

### Harness-Delta

- none
