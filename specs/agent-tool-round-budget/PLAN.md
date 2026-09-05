---
slug: agent-tool-round-budget
status: shipped
owner: minhtran3124
created: 2026-09-05
---

# Raise the effective tool-round budget: skip the no-op guard step, batch itinerary writes

## 1. Motivation

A live turn hit `GraphRecursionError` building a 6-day itinerary: `apps/api/app/agents/subagents/_base.py:255-264`
wires every specialist's ReAct loop as `assistant → trip_guard → tools → assistant`. `trip_guard`
is a real graph node (added for GH-113 to block a trip-scoped tool call deterministically when no
trip is selected), so it consumes one super-step on **every** round — including the overwhelming
common case where a trip is already active and the guard does nothing but
`return Command(goto="tools")`. With `agent_recursion_limit = 25` and 3 super-steps per round
(`3N + 1 ≤ 25`), a turn is capped at **8** tool-calling rounds. The failing turn needed 9: it ran
`recall_past_trips`, `search_places`, then `add_itinerary_item` once per day (the planner emits one
tool call per round), and died on round 9.

Checkpoint evidence for the failing turn (`specs/agent-tool-round-budget/SUMMARY.md` § Findings):
namespace `planner:032ed25d-…` recorded steps −1..25 inside one turn, 3 steps per round, 6 of the 8
completed rounds were `add_itinerary_item`.

Two independent, complementary fixes (both requested — "gộp 2 hướng 1 + 2"):

1. **Structural** — stop paying the guard's super-step when it cannot fire. Replace the
   dict-keyed `tools_condition` conditional edge with a router that decides `tools` vs
   `trip_guard` vs `END` directly: skip straight to `tools` unless the call actually needs a trip
   and none is selected. `trip_guard` stays a real node (Command-based, must run before `ToolNode`
   to block deterministically) — it is now reached only on the genuine blocking path. Fast-path
   rounds drop from 3 to 2 super-steps: the ceiling becomes `2N + 1 ≤ 25` → **12** rounds.
2. **Behavioral** — teach the planner to batch same-turn `add_itinerary_item` calls. `ToolNode`
   already runs every tool call in one `AIMessage` in a single `tools` super-step, so writing 3
   items in one round instead of 3 rounds cuts demand directly. This depends on model compliance
   (prose, not a graph guarantee), which is why it ships alongside the structural fix rather than
   instead of it.

Neither change touches the guard's blocking behavior (GH-113): a trip-scoped call with no active
trip still routes through `trip_guard`, still sets `awaiting_user`, still returns the same
`ToolMessage` errors.

## 2. Non-goals

- No change to `agent_recursion_limit` (rejected at investigation: pushes the wall back without
  removing the waste, and makes a genuinely-stuck loop run longer before failing).
- No change to `trip_guard`'s blocking logic, its `Command` shape, or `NO_ACTIVE_TRIP_MSG`.
- No change to `app/agents/prompt_map.py` — `trip_guard` remains a valid, listed inner node name;
  only how often it is *visited* changes, not its identity or prompt attribution.
- No cleanup of the 6 duplicate "Morning coffee at …" itinerary items left by the failed turn —
  that is a data cleanup, not a code fix; out of scope here.
- No change to `create_trip` + itinerary-item batching prohibition (planner v11 line 42-43): those
  still happen in separate steps because the new trip must be active before items can target it.

## Global Constraints

- Run every `Verify` from `apps/api/` with `../../.venv/bin/python`; each is one pipe-free command,
  <60s, never the whole suite.
- Surgical diffs: do not touch `app/agents/prompt_map.py`, `app/agents/constants.py`, or any file
  outside each task's Files list. Do not remove `trip_guard`'s own defensive
  `if not needing_trip or state.get("trip_id"): return Command(goto="tools")` check — it becomes
  unreachable in the fast path once the router is correct, but keeping it prevents the two decision
  points from silently diverging if either is edited later (Rule 3: don't delete pre-existing
  working code that isn't broken).
- Prompts are versioned: never edit `planner/v11.md`; add `planner/v12.md`, bump `active.yaml`, add
  a newest-first `CHANGELOG.md` entry. Precedent for an additive-only bump exists in this repo's
  `CHANGELOG.md` under "v3 — apply mizumi-ai patterns" (concierge/booking v2→v3): additive only,
  `diff v11.md v12.md` must print 0 lines starting with `<`. Editing a prompt `.md` / `active.yaml`
  does not hot-reload the running agent (`docker exec api-api-1 touch app/main.py`).
- Prompt tests assert on CONTENT only, never a version number (`tests/prompts/test_active_versions_load.py`
  documents why literal version pins were removed).
- Add import and usage in the same edit (the ruff-on-edit hook strips unused imports at save time).

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | A trip-scoped tool call with an active trip selected reaches `tools` directly from `assistant` — the compiled subgraph never visits `trip_guard` for that round | `../../.venv/bin/python -m pytest tests/agents/test_trip_guard.py -q -k skips_guard` | exit 0 |
| SC-2 | The no-trip blocking path is unchanged: a trip-scoped call with no trip selected still routes through `trip_guard`, sets `awaiting_user`, and returns the existing error `ToolMessage`s | `../../.venv/bin/python -m pytest tests/agents/test_trip_guard.py -q` | exit 0 |
| SC-3 | A sequential 10-round tool-calling turn (an active trip, one `add_itinerary_item` call per round) completes without `GraphRecursionError` under the unchanged `agent_recursion_limit=25` | `../../.venv/bin/python -m pytest tests/agents/test_trip_guard.py -q -k round_budget` | exit 0 |
| SC-4 | The existing 7-tool-chain recursion-headroom golden still passes unmodified | `../../.venv/bin/python -m pytest tests/agents/test_plan_everything.py -q` | exit 0 |
| SC-5 | Active planner prompt instructs batching same-turn `add_itinerary_item` calls into one round when several items are ready at once, without removing any v11 line | `../../.venv/bin/python -m pytest tests/prompts/test_planner_prompt.py -q` | exit 0 |
| SC-6 | Static node-name coverage (prompt-map inner-node list, agent-config no-config-row list) is unaffected by the routing change | `../../.venv/bin/python -m pytest tests/agents/test_prompt_map.py tests/agents/test_agent_config_coverage.py -q` | exit 0 |
| SC-7 | Lint clean on the touched files | `ruff check app/agents/subagents/_base.py app/prompts/planner tests/agents/test_trip_guard.py tests/prompts/test_planner_prompt.py` | exit 0 |

## 4. Tasks

### Task 1.1 — Skip the trip_guard super-step when it cannot block (wave 1)

- **Files:** app/agents/subagents/_base.py, tests/agents/test_trip_guard.py
- **Action:** Write the tests first. In `tests/agents/test_trip_guard.py`, add:
  1. `test_trip_scoped_call_skips_guard_when_trip_active` (maps to SC-1): compile a subagent with a
     tool whose `trip_id` param is `Annotated[str | None, InjectedState("trip_id"), ...] = None`
     (reuse the pattern already in this file / `tests/tools/test_trip_tools.py::_tool_node_graph`,
     but build the FULL subagent via `build_subagent`, not a bare `ToolNode`). Drive it with a
     `FakeLLM` (or the file's existing scripted-LLM helper) that emits one tool call for that tool,
     with `trip_id` already set in the initial state. Stream with `stream_mode="updates"` and
     collect the node keys yielded; assert `"trip_guard"` never appears among them while
     `"tools"` does.
  2. `test_sequential_ten_round_turn_fits_recursion_budget` (maps to SC-3): use a trivial,
     test-local trip-scoped tool defined inline in the test with `@tool` and
     `Annotated[str | None, InjectedState("trip_id")] = None` (no DB, no fixture — deliberately not
     `add_itinerary_item`, which needs a real DB row per `tests/tools/test_trip_tools.py::test_add_itinerary_item_injected_via_tool_node`
     and would add unnecessary fixture cost to a routing/step-count test). Script a plain
     `FakeLLM(responses=[...])` to emit 10 sequential single-tool-call `AIMessage`s for that tool
     followed by a final prose `AIMessage` (`FakeLLM._build_next` cycles a list of
     dict/str/AIMessage items in order — no reusable multi-call helper exists yet in this file, so
     script the list directly). Build the subagent via `build_subagent` with just that one tool,
     set `trip_id` in the initial state, and invoke the compiled subgraph with
     `{"recursion_limit": get_settings().agent_recursion_limit}` (default 25, do not hardcode).
     Assert it completes (no `GraphRecursionError`) and the final message is the prose answer.
     Comment the arithmetic this proves: 10 rounds × 2 super-steps + 1 = 21 ≤ 25 — this round count
     would need `3*10+1 = 31` super-steps under the old topology and would have failed.
  Keep every existing test in this file passing unmodified — they cover SC-2 (the blocking path)
  and must still pass verbatim, proving the fix does not touch that behavior.
  Then implement in `app/agents/subagents/_base.py`: add a router function next to
  `_make_trip_guard`:
  ```python
  def _route_after_assistant(needing_trip: frozenset[str]):
      def route(state: TravelAgentState) -> str:
          dest = tools_condition(state)
          if dest == END:
              return END
          if not needing_trip or state.get("trip_id"):
              return "tools"
          last = state["messages"][-1]
          calls = getattr(last, "tool_calls", None) or []
          if any(tc.get("name") in needing_trip for tc in calls):
              return "trip_guard"
          return "tools"
      return route
  ```
  Replace `builder.add_conditional_edges("assistant", tools_condition, {"tools": "trip_guard", END: END})`
  with `builder.add_conditional_edges("assistant", _route_after_assistant(needing_trip), {"tools": "tools", "trip_guard": "trip_guard", END: END})`.
  `needing_trip` is already computed above this line — reuse it, do not recompute. Do not change
  `_make_trip_guard` or the `trip_guard` node's own body.
- **Verify:** `../../.venv/bin/python -m pytest tests/agents/test_trip_guard.py tests/agents/test_plan_everything.py -q`
- **Done:** All tests in both files pass, including the 2 new ones; `ruff check app/agents/subagents/_base.py tests/agents/test_trip_guard.py` exits 0.
- **Criteria:** SC-1, SC-2, SC-3, SC-4
- **Interfaces:** Consumes langgraph's tools_condition helper and the existing _tools_needing_trip / _make_trip_guard / TravelAgentState / END symbols, all already imported in the module being edited. Produces `app/agents/subagents/_base.py`, `tests/agents/test_trip_guard.py`.

### Task 1.2 — Planner batches same-turn itinerary writes (wave 1)

- **Files:** app/prompts/planner/v12.md, app/prompts/active.yaml, app/prompts/CHANGELOG.md, tests/prompts/test_planner_prompt.py
- **Action:** Write `tests/prompts/test_planner_prompt.py` first (new file, mirrors the existing
  content-pin pattern in `tests/prompts/test_booking_prompt.py` — a parametrized/plain
  `registry.get(name)` string assertion, no version pinning): assert `registry.get("planner")`
  contains the literal tool name `add_itinerary_item` together with a batching instruction (assert
  the exact phrase `same response` appears in the sentence you add below), and assert it still
  contains the pre-existing "create the trip first, then add itinerary items in your next step"
  line (proves v11 content survived). Then:
  - `planner/v12.md` = copy of v11.md plus ONE new bullet under "How to Work" step 4 ("Write
    itinerary items with your tools once the traveller is happy."): add a sentence directly after
    it — "When several items are ready at once (e.g. filling out multiple days), call
    `add_itinerary_item` more than once in the SAME response instead of one item per turn, so a
    full itinerary does not exhaust the turn's tool-call budget." Do not reword or remove anything
    else; `diff v11.md v12.md` must print 0 lines starting with `<`.
  - `active.yaml`: `planner: 12`. `CHANGELOG.md`: newest-first entry
    `agent-tool-round-budget — skip the no-op trip_guard step; planner batches itinerary writes`,
    listing both the v12 addition and the `_base.py` routing change (code half), in the style of
    the existing `agent-budget-trip-context` entry.
- **Verify:** `../../.venv/bin/python -m pytest tests/prompts/test_planner_prompt.py tests/prompts/test_active_versions_load.py tests/api/prompts/test_prompt_registry_helpers.py -q`
- **Done:** Tests pass; `diff app/prompts/planner/v11.md app/prompts/planner/v12.md | grep -c '^<'` prints `0`.
- **Criteria:** SC-5
- **Interfaces:** Consumes the existing prompt registry (name → active version from active.yaml) and the existing planner v11 text. Produces `app/prompts/planner/v12.md`, `app/prompts/active.yaml`, `tests/prompts/test_planner_prompt.py`.

### Task 2.1 — Confirm static coverage is unaffected (wave 2)

- **Files:** none (verification-only task; no files changed)
- **Action:** After Task 1.1 lands, run the static coverage suites that reference the
  `trip_guard`/`planner/trip_guard` node name to confirm the routing change did not rename or drop
  the node (only how often it is visited changed).
- **Verify:** `../../.venv/bin/python -m pytest tests/agents/test_prompt_map.py tests/agents/test_agent_config_coverage.py -q`
- **Done:** Both files pass unmodified.
- **Criteria:** SC-6, SC-7
- **Interfaces:** Consumes the compiled graph's node names (unchanged by Task 1.1). Produces no new artifact — a confirmation-only Verify row for `specs/agent-tool-round-budget/SUMMARY.md`.

## 5. Risks

- **Router/guard divergence.** The new router and `trip_guard`'s own internal check duplicate the
  same "needs trip and none active" test. If one is edited without the other, the fast path could
  either skip a call that should be blocked (regression on GH-113) or route a safe call through the
  guard needlessly (silent regression back toward the old budget). Mitigated by SC-2 keeping every
  existing blocking test green, and by the constraint to change only the router, not the guard body.
- **Planner batching is prose, not a graph guarantee.** SC-5 proves the instruction is shipped;
  whether the model actually batches calls is a live-LLM behavior with no unit-test proof — recorded
  under `SUMMARY.md` § Not auto-verified, same as the structural fix's live-replay caveat.
- **12-round ceiling is still finite.** A itinerary long enough (13+ un-batched rounds) still fails;
  this plan raises the ceiling and lowers typical demand, it does not remove the limit.
- **Prompt not hot-reloaded** in the running container — needs `docker exec api-api-1 touch app/main.py`
  before a live replay.

## 6. Status Log

- 2026-09-05 — intake (`SUMMARY.md`, Lane normal / Confidence high); PLAN.md authored (2 tasks
  wave 1 + 1 verification task wave 2), status `proposed`.
- 2026-09-05 — tasks 1.1, 1.2 complete; commits 759876a, 902145a. Per-task reviews: both spec pass / quality approved. Minor findings (non-blocking, forwarded to final review): 1.1 controller reverted an unreported import-scope drift the implementer introduced in a test the brief said to keep unmodified (fixed before commit, amended sha 759876a); router and trip_guard duplicate the same decision with no test pinning they agree (optional follow-up). 1.2 shipped sentence uses lowercase "same response" per the machine-checked test contract, differing from the brief's capitalized example text (cosmetic); "No active trip yet" section does not explicitly scope the new batching rule to after a trip exists (reconcilable, no regression observed).
- 2026-09-05 — final review chain complete. Correctness: 6 FIND angles, 5 deduped locations, 1 fix-loop finding (score 75, commit 3125d2e), re-reviewed clean apart from one P3 advisory. Intent: pass, both directions delivered, GH-113 not regressed. Receipt written at 6cd3845. Next: finishing-a-development-branch.
