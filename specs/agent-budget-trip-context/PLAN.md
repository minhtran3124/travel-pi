---
slug: agent-budget-trip-context
status: proposed
owner: minhtran3124
created: 2026-09-05
---

# Budget agent: read trip context, estimate and set per-category caps

## 1. Motivation

Transcript that triggered this spec (verbatim intent in `SUMMARY.md`):

```
user: pls set simple budget for trip
bot: I can do that, but I'm still missing one detail: how many days is your trip?
```

The **budget** sub-agent is bound to `EXPENSE_TOOLS + get_trip_budget` only
(`app/tools/registry.py:59`). It cannot read the trip's dates/travelers (`get_trip_summary` is
planner/journal only), and **no agent tool sets a budget** — `TripService.set_trip_budget` is
reachable only via `POST /trips/{id}/budget`. `estimate_trip` (pure nights × travelers × rates)
is REST-only too. So the model improvises: it asks for the day count to do per-day arithmetic
itself, which also breaks the budget prompt guardrail "Don't estimate totals".

Approved direction (user, 2026-09-05): **per-category caps from the estimate, no schema change.**

Design decisions (this plan is the design record; no separate `design.md` — the single fork was
resolved by the user at intake):

- **Nights, not days.** `estimate_trip` takes `nights`. Derive `nights = max(1, (end_date - start_date).days)`
  from the trip when the model does not supply `nights` — only when BOTH `start_date` and `end_date` are set.
  If either date is missing AND the model passed no `nights`, the tool returns a guidance dict telling the
  model to ask.
- **Trip guard already covers the new tools.** `app/agents/subagents/_base.py::_tools_needing_trip` derives
  every `InjectedState("trip_id")` tool and `_make_trip_guard` intercepts the call before ToolNode when
  `trip_id` is None (sets `awaiting_user`). Both new tools use that annotation, so they are guarded
  automatically on the agent path; `_no_active_trip()` is the direct/MCP-path fallback.
- **Estimate → caps mapping** (`suggested_caps`, USD, 4 canonical `BudgetCategory` buckets):
  `flights ← breakdown.flights`, `hotels ← breakdown.accommodation`,
  `activities ← breakdown.activities`,
  `buffer ← breakdown.meals + breakdown.local_transport + (total_estimate - subtotal)`.
  Every estimate dollar lands in exactly one cap, so `sum(suggested_caps) == total_estimate`.
- **Two tools, not one.** `estimate_trip_budget` is read-only (safe to call speculatively);
  `set_trip_budget` is a write with *replace* semantics (same as the REST endpoint) and is called only
  after the traveller confirms the proposed caps. Keeps the HITL step explicit in the prompt.
- **Budget-domain only.** The two new tools are NOT appended to `TRIP_TOOLS` (planner/journal tool sets
  stay unchanged). `get_trip_summary` is additionally bound into the budget domain.
- **Supervisor routing.** "set / estimate a budget (caps) for the trip" → **budget**. Today v9 lists
  budget as "expenses, who-paid-what, balances, remaining budget" and planner v11 mentions "budget caps",
  so the request can land on planner; a supervisor v10 adds the rule + one example.

## 2. Non-goals

- No change to `TripBudgetSet` / `TripBudget` schemas, DB columns, or REST routes (no single-total cap).
- No change to `estimate_trip` rates or the REST `POST /trips/estimate` contract.
- No new tools for planner/journal/concierge/booking; no MCP `server.py` change (registry-driven exposure).
- No frontend change. No new dependency.
- No live-LLM eval run inside this plan (goldens are added; a baseline run is a follow-up, see `eval-harness-bypasses-db-config-and-context` memory).

## Global Constraints

- Run every `Verify` from `apps/api/` with `../../.venv/bin/python`; each is one pipe-free command, <60s, never the whole suite (the suite runs at `finishing-a-development-branch`).
- Tools keep the auto-derived schema: `user_id`/`trip_id` via `Annotated[..., InjectedState(...)]` with a `= None` default and inline `Field(description=...)`; **never** pass `args_schema=` (docs/solutions/agent/explicit-args-schema-breaks-tool-injection.md). When `trip_id is None` return `_no_active_trip()`; when `user_id is None` raise `ToolException` — exactly as `get_trip_budget` does.
- Wrap `AppError` with `tool_error(e)`; call `log_tool_call(name, {"trip_id": trip_id})` on the DB path; open the session with `session_scope()`.
- Prompts are versioned: never edit `budget/v2.md` or `supervisor/v9.md`; add `budget/v3.md` + `supervisor/v10.md`, bump `active.yaml`, add a newest-first `CHANGELOG.md` entry. Editing `.md`/`active.yaml` does not hot-reload the running agent (`docker exec api-api-1 touch app/main.py`).
- `set_trip_budget` goes into `_WRITE` (readOnly=False, destructive=False). `estimate_trip_budget` is read-only. Neither joins `_DESTRUCTIVE`.
- Do not touch `TRIP_TOOLS` membership, `EXPENSE_TOOLS`, or any other domain's binding.
- Add import and usage in the same edit (the ruff-on-edit hook strips imports that are unused at save time).
- Surgical diffs: no refactor of neighbouring tools, prompts, or tests.
- If `hooks/risk-corroboration.sh` flags `public-contract` on the registry/MCP surface at commit time, re-declare `Lane: high-risk` in `SUMMARY.md` rather than bypassing (memory `risk-corroboration-session-auth-false-positive`).

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | The budget domain binds `get_trip_summary`, `get_trip_budget`, `estimate_trip_budget`, `set_trip_budget` (plus expense tools); planner/journal tool sets are unchanged | `../../.venv/bin/python -m pytest tests/tools/test_tool_registry.py -q` | exit 0 |
| SC-2 | `set_trip_budget` persists per-category caps that `get_trip_budget` then reports (replace semantics: an omitted category becomes uncapped) | `../../.venv/bin/python -m pytest tests/tools/test_trip_budget_tools.py -q -k set_trip_budget` | exit 0 |
| SC-3 | `estimate_trip_budget` with no `nights`/`travelers` derives them from a dated trip and returns `suggested_caps` whose four values sum to `total_estimate` | `../../.venv/bin/python -m pytest tests/tools/test_trip_budget_tools.py -q -k derive` | exit 0 |
| SC-4 | `estimate_trip_budget` on a trip without dates and without `nights` returns a guidance dict containing the key `hint` and raises nothing | `../../.venv/bin/python -m pytest tests/tools/test_trip_budget_tools.py -q -k no_dates` | exit 0 |
| SC-5 | Both new tools return the no-active-trip guidance (not a KeyError/500) when `trip_id` is absent from state, hide `trip_id`/`user_id` from the model-facing schema, and are picked up by the subagent trip guard | `../../.venv/bin/python -m pytest tests/tools/test_trip_tools_no_active_trip.py tests/agents/test_trip_guard.py -q` | exit 0 |
| SC-6 | Active budget prompt names all three tools with a "load the trip first / ask nights only when the trip has no dates / confirm before set" flow; active supervisor prompt routes budget-cap requests to **budget** | `../../.venv/bin/python -m pytest tests/prompts/test_budget_prompt.py tests/prompts/test_active_versions_load.py -q` | exit 0 |
| SC-7 | MCP server exposes `estimate_trip_budget` (readOnly) and `set_trip_budget` (write, non-destructive) alongside existing trip tools | `../../.venv/bin/python -m pytest tests/mcp/test_mcp_server.py -q` | exit 0 |
| SC-8 | Eval datasets still load/validate with the new budget goldens (routing + tools) | `../../.venv/bin/python -m pytest tests/eval/test_datasets.py tests/eval/test_run_deepeval.py -q` | exit 0 |
| SC-9 | Lint clean on app and every test directory this plan touches (whole `tests/` has pre-existing B017/F811 findings on `main`, out of scope) | `ruff check app tests/tools tests/mcp tests/prompts tests/agents/test_trip_guard.py` | exit 0 |

## 4. Tasks

### Task 1.1 — `estimate_trip_budget` + `set_trip_budget` agent tools (wave 1)

- **Files:** app/tools/trip_tools.py, tests/tools/test_trip_budget_tools.py
- **Action:** Write the tests first (`tests/tools/test_trip_budget_tools.py`, using the `agent_db` /
  `trip_id` fixtures from `tests/tools/conftest.py`; create a second, dated trip in-test via
  `TripService(s, "test-user-1").create_trip(TripCreate(title=..., start_date=date(2026,10,1), end_date=date(2026,10,4), travelers=2))`).
  Then add two `@tool`s at the end of `app/tools/trip_tools.py`, following `get_trip_budget` exactly for
  injected args, `_no_active_trip()`, `ToolException`, `session_scope`, `log_tool_call`, `tool_error`:
  1. `set_trip_budget(flights: float|None, hotels: float|None, activities: float|None, buffer: float|None, user_id=Injected, trip_id=Injected) -> dict`
     — each cap `Annotated[float | None, Field(ge=0, description=...)] = None`; builds `TripBudgetSet` and
     returns `dump(TripService(s, user_id).set_trip_budget(trip_id, req))`. Docstring must state the
     replace semantics ("omitted categories become uncapped") and "call only after the traveller confirms".
  2. `estimate_trip_budget(nights: int|None=None, travelers: int|None=None, meal_style: MealStyle=MID, activity_level: ActivityLevel=SOME, flight_total_usd: float|None=None, hotel_price_per_night_usd: float|None=None, user_id=Injected, trip_id=Injected) -> dict`
     — loads the trip via `TripService(s, user_id).get_trip(trip_id)`; when `nights is None` derives
     `max(1, (end_date - start_date).days)` from the trip's dates, when `travelers is None` uses the trip's
     `travelers`; if `nights` is still unknown (trip has no dates) return
     `{"error": "trip_dates_unknown", "hint": "Ask the traveller how many nights the trip is (or its dates); do not guess."}`
     without calling `estimate_trip`. Otherwise call `estimate_trip(TripEstimateRequest(city=trip.city, nights=..., travelers=..., ...))`
     and return `dump(response) | {"suggested_caps": {...}}` using the mapping in §1
     (`buffer = meals + local_transport + (total_estimate - subtotal)`, each `round(x, 2)`).
  Every model-facing parameter on BOTH tools carries `Annotated[..., Field(description=...)]`
  (`tests/tools/test_tool_registry.py::test_every_tool_has_explicit_described_schema` fails otherwise).
  In `estimate_trip_budget` also catch `except ValueError as e: raise ToolException(str(e)) from e` around
  the `TripEstimateRequest(...)` construction (pydantic `ValidationError` on `nights=0` or a negative price),
  mirroring `add_itinerary_item`.
  Do NOT add either tool to `TRIP_TOOLS`; export them as module-level names. Tests must cover: SC-2
  (set then `get_trip_budget` shows caps; second call with one category omitted uncaps it), SC-3 (dated
  trip → `nights == 3`, `travelers == 2`, `sum(suggested_caps.values()) == pytest.approx(total_estimate)`),
  SC-4 (undated `trip_id` fixture → dict with `hint`, no exception; a trip with only `start_date` set →
  same guidance), an explicit-`nights` override on the undated trip, `nights=0` → `ToolException`, and one `ToolNode` injection run of `set_trip_budget` through a `TravelAgentState` graph
  (copy `_tool_node_graph` from `tests/tools/test_trip_tools.py`).
- **Verify:** `../../.venv/bin/python -m pytest tests/tools/test_trip_budget_tools.py -q`
- **Done:** New test module passes; `ruff check app/tools/trip_tools.py tests/tools/test_trip_budget_tools.py` exits 0; `tool.tool_call_schema.model_json_schema()["properties"]` for both tools contains neither `user_id` nor `trip_id`.
- **Criteria:** SC-2, SC-3, SC-4
- **Interfaces:** Consumes existing TripService.get_trip / set_trip_budget, the pure estimate_trip function, the TripEstimateRequest and TripBudgetSet schemas, the MealStyle and ActivityLevel enums, and the injected-arg pattern already used in trip_tools.py. Produces `app/tools/trip_tools.py::estimate_trip_budget`, `app/tools/trip_tools.py::set_trip_budget`, `tests/tools/test_trip_budget_tools.py`.

### Task 1.2 — Budget prompt v3 + supervisor v10 (wave 1)

- **Files:** app/prompts/budget/v3.md, app/prompts/supervisor/v10.md, app/prompts/active.yaml, app/prompts/CHANGELOG.md, tests/prompts/test_budget_prompt.py
- **Action:** Write `tests/prompts/test_budget_prompt.py` first: assert on CONTENT only, never on a version
  number (`tests/prompts/test_active_versions_load.py` records that literal pins were removed because they broke
  on every bump): `registry.get("budget")` contains the literal tool names `get_trip_summary`,
  `estimate_trip_budget`, `set_trip_budget` and the string `trip_dates_unknown`; `registry.get("supervisor")`
  contains the phrase `budget caps`. Then:
  - `budget/v3.md` = copy of v2 + a `## How to Work` extension: (1) call `get_trip_summary` first to learn
    dates, travelers and existing caps; (2) for "set / plan a (simple) budget": call `estimate_trip_budget`
    (pass `nights` only if the traveller stated it — otherwise let the tool derive from the trip), present the
    `suggested_caps` per category with the `assumptions`, and ask the traveller to confirm or adjust;
    (3) call `set_trip_budget` only after explicit confirmation, and say that it replaces all caps;
    (4) ask "how many nights / what dates" ONLY when `estimate_trip_budget` returns `trip_dates_unknown`.
    Guardrail addition: "Never compute per-day or total figures yourself — the estimate tool does it."
    Keep every v2 rule; add nothing else.
  - `supervisor/v10.md` = copy of v9; extend the **budget** bullet to
    "expenses, who-paid-what, balances, remaining budget, **and setting / estimating the trip's budget caps**";
    add one routing example `"Set a simple budget for my trip" → **budget**`. No other edits.
  - `active.yaml`: `budget: 3`, `supervisor: 10`. `CHANGELOG.md`: newest-first entry titled
    `agent-budget-trip-context — budget agent reads the trip and sets caps` listing both bumps and the
    (code-half) new tools, in the style of the `multi-intent-single-path` entry.
- **Verify:** `../../.venv/bin/python -m pytest tests/prompts/test_budget_prompt.py tests/prompts/test_active_versions_load.py tests/prompts/test_registry.py tests/api/prompts/test_prompt_registry_helpers.py -q`
- **Done:** Tests pass; `diff app/prompts/budget/v2.md app/prompts/budget/v3.md` prints 0 lines starting with `<` (v3 only adds); `diff app/prompts/supervisor/v9.md app/prompts/supervisor/v10.md` prints exactly 1 line starting with `<` (the rewritten budget bullet).
- **Criteria:** SC-6
- **Interfaces:** Consumes the prompt registry (name → active version from active.yaml) and the existing budget v2 / supervisor v9 texts. Produces `app/prompts/budget/v3.md`, `app/prompts/supervisor/v10.md`, `tests/prompts/test_budget_prompt.py`.

### Task 1.3 — Eval goldens for the "set a simple budget" flow (wave 1)

- **Files:** eval/datasets/routing.json, eval/datasets/tools.json
- **Action:** Append to `routing.json`: `{"input": "Set a simple budget for my trip", "expected": "budget"}`
  and `{"input": "Đặt ngân sách đơn giản cho chuyến đi của mình", "expected": "budget"}`. Append to
  `tools.json` one case: `{"input": "Set a simple budget for my trip", "expected_flow": "budget", "expected_tools": ["get_trip_summary"]}`.
  Known at planning time: `eval/harness.py` invokes the graph with `trip_id: None` and a bare
  `AgentContext()`; `_tools_called` reads `AIMessage.tool_calls` (what the model ATTEMPTED), and tool
  matching is deepeval's `ToolCorrectnessMetric` over that list vs `expected_tools`. With no trip in state
  the trip guard (`_base.py::_make_trip_guard`) intercepts the call before ToolNode, so the tool never
  executes — the observable this golden pins is "the model attempts `get_trip_summary` first instead of
  asking for a day count". Do not add new metric keys.
- **Verify:** `../../.venv/bin/python -m pytest tests/eval/test_datasets.py tests/eval/test_run_deepeval.py -q`
- **Done:** Dataset tests pass; `python -c "import json;json.load(open('eval/datasets/routing.json'));json.load(open('eval/datasets/tools.json'))"` exits 0; routing.json has 2 more entries and tools.json 1 more than on `main`.
- **Criteria:** SC-8
- **Interfaces:** Consumes the dataset shapes read by eval/loader.py (input / expected_flow / expected_tools) and eval/run_eval.py (input / expected). Produces `eval/datasets/routing.json`, `eval/datasets/tools.json` (extended).

### Task 2.1 — Bind the tools into the budget domain + annotations + MCP/no-trip tests (wave 2)

- **Files:** app/tools/registry.py, tests/tools/test_tool_registry.py, tests/tools/test_trip_tools_no_active_trip.py, tests/mcp/test_mcp_server.py, tests/agents/test_trip_guard.py
- **Action:** Tests first: in `test_tool_registry.py` extend `test_get_tools_for_groups` so `budget` contains
  `{"add_expense","get_trip_budget","get_trip_summary","estimate_trip_budget","set_trip_budget"}` and add
  an assertion that `estimate_trip_budget`/`set_trip_budget` are NOT in planner, journal, concierge, booking;
  add `TOOL_METADATA["set_trip_budget"] == {"readOnly": False, "destructive": False}` and
  `TOOL_METADATA["estimate_trip_budget"] == {"readOnly": True, "destructive": False}`. In
  `test_trip_tools_no_active_trip.py` add the two new tools to the existing parametrize list (with the
  minimal model-facing args each needs, e.g. `{}` for estimate, `{"flights": 100}` for set) so all three
  absent-trip tests and the schema tests cover them. In `tests/mcp/test_mcp_server.py` extend
  `test_create_trip_excluded_but_other_trip_tools_exposed` (or add one test) asserting both new tool names
  are exposed and `set_trip_budget` is not marked destructive. In `tests/agents/test_trip_guard.py` add one
  test asserting `_tools_needing_trip(get_tools_for("budget"))` contains `estimate_trip_budget` and
  `set_trip_budget` (pins SC-5 on the agent path, not only the raw ToolNode path). Then edit `app/tools/registry.py`:
  `from app.tools.trip_tools import TRIP_TOOLS, create_trip, estimate_trip_budget, set_trip_budget` (same
  import line); `"budget": EXPENSE_TOOLS + [t for t in TRIP_TOOLS if t.name in {"get_trip_budget", "get_trip_summary"}] + [estimate_trip_budget, set_trip_budget]`;
  add `"set_trip_budget"` to `_WRITE`. Nothing else in the file changes.
- **Verify:** `../../.venv/bin/python -m pytest tests/tools/test_tool_registry.py tests/tools/test_trip_tools_no_active_trip.py tests/mcp/test_mcp_server.py tests/agents/test_trip_guard.py -q`
- **Done:** The four test modules pass; `ruff check app tests/tools tests/mcp tests/prompts tests/agents/test_trip_guard.py` exits 0; `git diff --stat main -- app/tools/registry.py` shows ≤ 6 changed lines.
- **Criteria:** SC-1, SC-5, SC-7, SC-9
- **Interfaces:** Consumes `app/tools/trip_tools.py::estimate_trip_budget`, `app/tools/trip_tools.py::set_trip_budget` (Task 1.1), the existing _meta / TOOL_METADATA derivation and the MCP server's filtering rules. Produces `app/tools/registry.py` (budget binding + `_WRITE`), `tests/tools/test_tool_registry.py`, `tests/mcp/test_mcp_server.py`, `tests/tools/test_trip_tools_no_active_trip.py` (extended).

## 5. Risks

- **public-contract gate at commit.** New tools appear on the MCP tool list (registry-driven). If
  `risk-corroboration.sh` flags it, re-declare `Lane: high-risk` in `SUMMARY.md`; do not narrow the diff.
- **Weak proof on the actual chat behaviour.** Unit tests prove the tools and the prompt text, not that
  the LLM stops asking for days. Mitigation: goldens (Task 1.3) + a manual 2-turn replay against the Docker
  agent after `touch app/main.py`, recorded under `Not auto-verified` in SUMMARY.
- **Routing collision planner ↔ budget.** Planner v11 mentions "budget caps"; supervisor v10 example is
  the tie-breaker. If the routing golden fails on a baseline run, follow up with a planner prompt bump
  (out of scope here).
- **Eval harness has no active trip.** The trip guard intercepts every trip tool there, so goldens can only
  pin "attempts `get_trip_summary` first" (from `AIMessage.tool_calls`), not the estimate/set path; end-to-end proof of that path is the manual replay above.
- **Prompt not hot-reloaded** in the running container (`prompt-changes-need-graph-rebuild-not-hot-reloaded`).
- **Stale local `travel.db`**: no ORM change here, so not expected to bite; `budget_caps` column already exists.

## 6. Status Log

- 2026-09-05 — intake (`SUMMARY.md`, Lane normal / Confidence medium); user approved default direction
  (per-category caps from estimate, no schema change); PLAN.md authored, status `proposed`.
- 2026-09-05 — worktree `.worktrees/feat-agent-budget-trip-context` on `feat/agent-budget-trip-context` off `main` 240aa5a; baseline: 103 targeted tests pass, `ruff check app` clean, `tests/` has pre-existing findings → SC-9 narrowed.
- 2026-09-05 — advisory plan review: REVISE (6 text objections, all applied: both-dates rule, trip-guard
  mechanism in Task 1.3, content-only prompt tests, ValueError handling, described schema fields,
  machine-decidable prompt diffs) → re-checked with `check_plan_contract.py`.
