---
slug: gh-166-list-trips-tool
status: active
owner: minhtran3124
created: 2026-09-09
---

# gh-166 — `list_trips` agent tool

## 1. Motivation

Asked "how many trips i have?", the agent answers from the single active `trip_id` and states it
as the complete set. It has no tool that lists a user's trips: `TripService.list_trips()` exists
and is served as `GET /trips`, but is absent from `app/tools/`. See `design.md` (approved) and
`research-brief.md` (Deep).

## 2. Non-goals

- `select_trip` / any mid-turn rebinding of `TravelAgentState.trip_id` (`ESCALATIONS.md` E001-A).
  Pulling a non-active trip's itinerary detail stays open on #166.
- Exposing `list_trips` over MCP (E003-B).
- Fixing `TripRepo.list_trips`'s unfiltered `select(models.TripItem)` — pre-existing.
- Building a seeded-trip eval fixture (`eval/adapters/db_oracle.py` records this gap).
- Claiming a fix for minhtran3124/travel-pi#150.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|---|---|---|---|
| SC-1 | A user with 2 trips gets `count: 2` and both titles, newest first | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_list_trips.py -q` | exit 0 |
| SC-2 | The payload carries no trip id and no full item list — only an item count | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_list_trips.py -q -k projection` | exit 0 |
| SC-3 | `list_trips` is absent from the MCP surface while `get_trip_summary` is still served | `cd apps/api && ../../.venv/bin/python -m pytest tests/mcp/test_mcp_server.py -q` | exit 0 |
| SC-4 | Another user's trips are never returned, and a missing `user_id` raises | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_list_trips.py -q -k owner` | exit 0 |
| SC-5 | The tool is bound to planner and journal, not to budget or concierge, and is `readOnly` | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_tool_registry.py -q` | exit 0 |
| SC-6 | `active.yaml` points at the prompt versions that carry the two-trigger rule | `cd apps/api && ../../.venv/bin/python scripts/check_gh166_prompt_wiring.py` | exit 0 |
| SC-7 | The tool's return value is JSON-serializable (dates stringified, not `date` objects) | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_list_trips.py -q -k json` | exit 0 |
| SC-8 | Both goldens load and validate against the eval taxonomy, and the updated golden declares `tools_expected` | `cd apps/api && ../../.venv/bin/python -m pytest tests/eval -q` | exit 0 |
| SC-9 | The shared trip-context label keeps its `Current trip context` prefix and states it is one open trip, not the list | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_state_system_prompt.py -q` | exit 0 |
| SC-10 | The new golden's `expected_flow` is non-empty and names a flow the supervisor can route to | `cd apps/api && ../../.venv/bin/python scripts/check_gh166_golden_flow.py` | exit 0 |
| SC-11 | The SUMMARY's `Baseline decision:` line carries the token `refreshed` or `accepted` and two numeric pass_rate values | `cd apps/api && ../../.venv/bin/python scripts/check_gh166_baseline_note.py` | exit 0 |

SC-6 and SC-9 reach the **traceability** tier only. SC-6 proves the prompt wiring — `active.yaml`
resolves to the versioned file that carries the rule text. SC-9 proves the rendered `state.py`
label contains the new wording; it involves no prompt version at all. Neither shows the model
obeys. The behavioral evidence is the eval
run in Task 4.1, and it is judged, not deterministic. Recorded in `SUMMARY.md`
→ `### Not auto-verified`. SC-10 and SC-11 likewise prove that a decision was recorded, not that
the decision was right — the eval run behind them is judged and paid, and is run manually
(Task 4.1).

## Global Constraints

- Python 3.14 in the local venv, **3.12 in Docker** — no version-sensitive syntax.
- No new dependency. No change to `requirements.txt`.
- Do **not** hand-author `@tool(args_schema=...)`; keep the auto-derived schema and put
  model-facing text in `Annotated[..., Field(description=...)]`
  (`docs/solutions/agent/explicit-args-schema-breaks-tool-injection.md`).
- Both injected params carry an explicit `= None` default.
- Project from `dump(trip)`, never from raw ORM/Pydantic attributes — `dump()` is
  `model_dump(mode="json")` and is what stringifies `date` fields.
- `list_trips` must **not** return `_no_active_trip()` when `trip_id` is `None`: having no open
  trip is a valid state for this question.
- Editing a `vN.md` without bumping `active.yaml` is a silent no-op
  (`docs/solutions/agent/supervisor-active-yaml-is-a-pointer.md`). Never edit prose in
  `active.yaml` itself.
- Never tell an agent to call a tool it does not bind (`concierge` has no trip tools) —
  `docs/solutions/agent/concierge-hotel-tool-choice.md`.
- `rules/behavior.md` §3: no adjacent refactors. The unfiltered `TripItem` query stays as it is.
- The three `check_gh166_*.py` helpers live in `apps/api/scripts/` and are **kept**, not deleted at
  branch close: each one is a Success-Criteria check and must stay re-runnable. They are linted by
  `ruff check app scripts` like the rest of that directory.
- Stage and commit as **separate** commands (a PreToolUse hook blocks the compound form).
- The ruff-on-edit hook deletes imports added before their first use — add import and usage
  together, then `ruff check app scripts`.
- Task `Verify` is scoped to directories (`tests/tools/`, `tests/mcp/`), never to one new file
  alone. The full suite runs at `finishing-a-development-branch`, not in a task.

## 4. Tasks

### Task 1.1 — `list_trips` tool + unit tests (wave 1)

- **Files:** apps/api/app/tools/trip_tools.py, apps/api/tests/tools/test_list_trips.py
- **Action:** Write the tests first, then the tool. Add `list_trips(user_id=None, trip_id=None)`
  to `trip_tools.py` next to `get_trip_summary`, mirroring its shape: both params
  `Annotated[str | None, InjectedState(...), Field(description=...)] = None`, no explicit
  `args_schema`, `log_tool_call`, `session_scope()`, `AppError → tool_error`. Raise
  `ToolException` when `user_id is None`. When `trip_id is None`, return a normal result — every
  `is_active` is `False` — and do **not** call `_no_active_trip()`.
  Build the payload as `{"count": len(trips), "trips": [...]}`, each entry projected from
  `dump(trip)`: `title`, `city`, `start_date`, `end_date`, `travelers`, `items` (the *count*,
  `len(d["items"])`), and `is_active` (`d["id"] == trip_id`). Do not emit `id`.
  Append `list_trips` to the `TRIP_TOOLS` list. Write the docstring as the model-facing
  description: what it returns, and that it is the only way to know how many trips exist.
  Tests: two trips with **explicit distinct `created_at`** values assert `count == 2` and
  newest-first order; `is_active` marks only the injected `trip_id`, and none when it is `None`;
  zero trips return `{"count": 0, "trips": []}`; `user_id=None` raises `ToolException`; a second
  user's trips are never returned (`-k owner`); the payload has no `id` key and `items` is an int
  (`-k projection`); `json.dumps(result)` succeeds (`-k json`).
- **Verify:** `cd apps/api && ../../.venv/bin/ruff check app && ../../.venv/bin/python -m pytest tests/tools/ -q`
- **Done:** `tests/tools/` passes; `list_trips` is in `TRIP_TOOLS`; the payload contains no `id`
  key and `json.dumps` of it succeeds.
- **Criteria:** SC-1, SC-2, SC-4, SC-7
- **Interfaces:** Consumes: the existing TripService.list_trips and the dump / session_scope / tool_error / log_tool_call helpers. Produces: `apps/api/app/tools/trip_tools.py`, `apps/api/tests/tools/test_list_trips.py`.

### Task 1.2 — Shared `trip_context` label states it is one trip, not the list (wave 1)

- **Files:** apps/api/app/agents/state.py, apps/api/tests/agents/test_state_system_prompt.py
- **Action:** In `system_with_summary`, replace the `Current trip context:` label with this exact
  string, and nothing else:
  `Current trip context (the ONE trip currently open — this is not a list of the traveller's trips, and says nothing about how many they have):`
  **Keep the leading `Current trip context` prefix verbatim**: `tests/agents/test_state_system_prompt.py`
  and `tests/agents/test_trip_facts.py` both assert on that exact substring, so dropping it breaks
  a test in a file this task does not own. Keep the label purely negative — name no tool — because
  this string reaches every sub-agent including `concierge`, which binds no trip tools. Extend
  `tests/agents/test_state_system_prompt.py` with an assertion that the rendered system message
  contains `is not a list of the traveller's trips` when `trip_context` is set, and that no tool
  name appears in the label.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/ -q`
- **Done:** `tests/agents/` passes; the rendered message contains both `Current trip context` and
  `is not a list of the traveller's trips`; the label contains no tool name.
- **Criteria:** SC-9
- **Interfaces:** Consumes: the trip_context state field written by load_context. Produces: `apps/api/app/agents/state.py`, `apps/api/tests/agents/test_state_system_prompt.py`.

### Task 2.1 — Exclude `list_trips` from the MCP surface (wave 2)

- **Files:** apps/api/app/mcp/server.py, apps/api/tests/mcp/test_mcp_server.py
- **Action:** In `build_mcp_server`, add a by-name exclusion for `list_trips` alongside the
  existing `if meta["destructive"]: continue` check — this is the first by-name exclusion in the
  file, so introduce a small named constant (e.g. `_MCP_EXCLUDED_BY_NAME = {"list_trips"}`) rather
  than an inline literal. Comment it with the reason: FastMCP derives the served schema from the
  raw signature, so `user_id` is a caller-supplied argument on an unauthenticated surface, and
  `list_trips` would need only a `user_id` to dump a user's whole inventory (E003-B). Add a test
  asserting `list_trips` is absent from `list_tools()` while `get_trip_summary` is present.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/mcp/ -q`
- **Done:** `tests/mcp/` passes; `list_trips` is not in `list_tools()`; `get_trip_summary`,
  `search_flights` and `estimate_trip_budget` still are.
- **Criteria:** SC-3
- **Interfaces:** Consumes: the tool list and metadata exported by the registry module. Produces: `apps/api/app/mcp/server.py`, `apps/api/tests/mcp/test_mcp_server.py`.

### Task 2.2 — Registry binding assertions (wave 2)

- **Files:** apps/api/tests/tools/test_tool_registry.py
- **Action:** Add assertions that `list_trips` is bound to the `planner` and `journal` domains,
  is **not** bound to `budget` or `concierge`, and that `TOOL_METADATA["list_trips"]` is
  `readOnly=True, destructive=False`. No production file changes: the binding comes from Task 1.1
  appending to `TRIP_TOOLS`, and `budget`'s name allowlist excludes it with no edit.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_tool_registry.py -q`
- **Done:** The four bindings and both metadata flags are asserted and pass.
- **Criteria:** SC-5
- **Interfaces:** Consumes: the domain bindings and metadata exported by the registry module. Produces: `apps/api/tests/tools/test_tool_registry.py`.

### Task 2.3 — Two-trigger prompt rule: planner v14, journal v3 (wave 2)

- **Files:** apps/api/app/prompts/planner/v14.md, apps/api/app/prompts/journal/v3.md, apps/api/app/prompts/active.yaml, apps/api/app/prompts/CHANGELOG.md, apps/api/scripts/check_gh166_prompt_wiring.py
- **Action:** Copy `planner/v13.md` → `v14.md` and `journal/v2.md` → `v3.md`, then add one rule to
  each with **two** triggers:
  (1) *counting* — to say how many trips the traveller has, or to list them, call `list_trips`;
  never count from the trip context, which shows one open trip only;
  (2) *naming* — when the traveller refers to a trip that is not the open one, call `list_trips`
  first; if it is there, treat it as an existing trip and say which trip is currently open —
  never offer to draft it as a new idea. Do not promise to show its itinerary (out of scope).
  Bump `active.yaml` to `planner: 14`, `journal: 3` and add a `CHANGELOG.md` entry for each.
  The Verify also runs `tests/api/prompts/test_prompt_registry_helpers.py`, which asserts every
  `active.yaml` pin resolves to an existing `vN.md` — that catches a bump-without-file directly,
  rather than leaving it to the new script alone.
  Add `scripts/check_gh166_prompt_wiring.py`: it resolves both prompts through
  `app.prompts.registry.get(...)` and exits non-zero unless the returned text mentions
  `list_trips` for both agents — proving the pointer resolves to the file that carries the rule,
  not merely that a file on disk contains it.
- **Verify:** `cd apps/api && ../../.venv/bin/python scripts/check_gh166_prompt_wiring.py && ../../.venv/bin/python -m pytest tests/prompts/ tests/api/prompts/test_prompt_registry_helpers.py -q`
- **Done:** `active.yaml` reads `planner: 14` / `journal: 3`; the wiring script exits 0;
  `tests/prompts/` passes.
- **Criteria:** SC-6
- **Interfaces:** Consumes: the prompt registry and the v13 / v2 prompt bodies. Produces: `apps/api/app/prompts/planner/v14.md`, `apps/api/app/prompts/journal/v3.md`, `apps/api/app/prompts/active.yaml`, `apps/api/scripts/check_gh166_prompt_wiring.py`.

### Task 3.1 — Eval goldens: one added, one updated (wave 3)

- **Files:** apps/api/eval/datasets/journal.json, apps/api/tests/eval/test_datasets.py
- **Action:** Add one golden — `capability: "journal"`, `scenario: "happy"`, `language: "en"`,
  `suite: "full"`, `input: "how many trips do I have?"`, `expected_tools: ["list_trips"]`,
  `metrics: ["flow_match", "tools_expected", "reply_language"]`, and a `notes` line recording that
  the runner hardcodes `user_id = "eval"` with no seeded trips, so this golden proves routing and
  tool selection, not the count. Leave `expected_flow` unset in this task — Task 4.1 fills it from
  the observed route.
  Pin the new golden's `id` to `journal-happy-en-02` (ids are required and must be unique —
  `JsonDatasetStore` raises on a duplicate).
  Update the existing `journal-ambiguous-vi-01` by adding `expected_tools: ["list_trips"]`,
  **adding `tools_expected` to its `metrics` list**, and appending to its note that #150 is
  unchanged by this work. Without that metric the new expectation is inert: goldens declare their
  metrics explicitly and `DEFAULT_METRICS_BY_CAPABILITY` is empty, so a check absent from the list
  never runs. That golden is the only behavioral evidence for the naming trigger. Do not add an English near-twin: two
  correlated cases in a capability already below threshold is what moves the gate.
  **`tests/eval/test_datasets.py` must be edited in the same task**, for two reasons.
  (a) `test_total_case_count_at_least_60` asserts `len(...) == 102` — an exact equality despite
  its name — so a 103rd golden turns that suite red; bump the constant to 103.
  (b) Nothing under `tests/eval/` currently decides SC-8's metrics clause: add an assertion that
  `journal-ambiguous-vi-01` declares `tools_expected` in its `metrics`, so the criterion is
  decided by a check rather than by reading the diff.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/eval -q`
- **Done:** `tests/eval` passes with the count constant at 103; `journal.json` has exactly one new entry (`journal-happy-en-02`)
  and one modified entry (`journal-ambiguous-vi-01`), and that modified entry's `metrics` list
  contains `tools_expected`.
- **Criteria:** SC-8
- **Interfaces:** Consumes: the capability and scenario taxonomy used by the eval dataset store. Produces: `apps/api/eval/datasets/journal.json`, `apps/api/tests/eval/test_datasets.py`.

### Task 4.1 — Observe the route, then decide on a supervisor bump (wave 4)

- **Files:** apps/api/eval/datasets/journal.json, apps/api/scripts/check_gh166_golden_flow.py, apps/api/app/prompts/supervisor/v12.md, apps/api/app/prompts/active.yaml, apps/api/app/prompts/CHANGELOG.md
- **Action:** Run the `journal` capability slice **manually, inside the Docker `api` container** —
  `docker compose exec api python -m eval --suite full --capability journal --out eval/reports/gh166.json`.
  It must run in the container: the eval harness invokes the graph directly, so on the host
  `AgentConfigCache` is unpopulated and every node falls back to the env model
  (`docs/solutions/` eval-bypasses-db-config). This run **invokes the real agent, needs a provider
  key, costs money, and includes judged metrics** (`format_quality` on two goldens in this slice) —
  it is not deterministic and takes minutes, so it is not this task's `Verify`. Record it under
  `### Not auto-verified` in the SUMMARY with the report path.
  Read which sub-agent handled `journal-happy-en-02` and write that value into the golden's
  `expected_flow`.
  If the observed route was `planner` or `journal`, make **no** supervisor change and say so in the
  SUMMARY — the routing was already right. Only if it landed on an agent that binds no trip tools
  (e.g. `concierge`), copy `supervisor/v11.md` → `v12.md`, add one routing example for "how many
  trips do I have" / "list my trips", bump `active.yaml` to `supervisor: 12`, add a CHANGELOG
  entry, and re-run the slice. Never bump the supervisor without that observation.
  Add `scripts/check_gh166_golden_flow.py`: it loads `journal.json` and exits non-zero unless
  `journal-happy-en-02` has a non-empty `expected_flow` whose value is a key of `TOOLS_BY_DOMAIN`
  in `app/tools/registry.py` — that mapping is the only canonical set of sub-agent names
  (`TravelAgentState.current_flow` is a plain `str`, so there is no enum to read). Do not
  hardcode a second list. On rejection the script must print the observed value, so the manual
  step stays diagnosable.
- **Verify:** `cd apps/api && ../../.venv/bin/python scripts/check_gh166_golden_flow.py && ../../.venv/bin/python -m pytest tests/eval -q`
- **Done:** `journal-happy-en-02` carries a non-empty `expected_flow`; the wiring check and
  `tests/eval` exit 0; a `supervisor/v12.md` exists only when the observed route bound no trip
  tools, and the SUMMARY names the branch taken and the report path.
- **Criteria:** SC-10
- **Interfaces:** Consumes: the goldens from Task 3.1 and the tool binding from Task 1.1. Produces: `apps/api/scripts/check_gh166_golden_flow.py`, `apps/api/eval/datasets/journal.json`.

### Task 5.1 — Baseline decision (wave 5)

- **Files:** specs/gh-166-list-trips-tool/SUMMARY.md, apps/api/scripts/check_gh166_baseline_note.py, apps/api/eval/baselines/main.json
- **Action:** Runs **after** Task 4.1 — it reads that task's report, so it cannot share its wave.
  Compare the run against the pinned baseline and decide, explicitly, between refreshing
  `eval/baselines/main.json` and accepting the delta. The gate reads the **`journal` capability
  pass_rate**, not case count — `evalkit/baseline.py` skips a `golden_id` present in only one
  report — and `journal` is already in `capabilities_below_threshold`. Write into the SUMMARY a
  `### Verify` row plus a `Baseline decision:` line naming the branch taken and the `journal`
  pass_rate before and after. Refresh the baseline only from a full judged run; if none was run,
  say so under `### Not auto-verified` and leave `main.json` untouched rather than let a stale
  baseline appear to cover the new golden.
  Add `scripts/check_gh166_baseline_note.py`: it exits non-zero unless the SUMMARY contains a
  `Baseline decision:` line carrying **both** one of the two fixed branch tokens `refreshed` /
  `accepted` **and** two numeric pass_rate values — so the check decides both halves of SC-11, not
  only that some line exists. It must resolve the repo root explicitly
  (`Path(__file__).resolve().parents[3]`) rather than opening a cwd-relative path, since it runs
  from `apps/api` but reads a file at the repo root.
- **Verify:** `cd apps/api && ../../.venv/bin/python scripts/check_gh166_baseline_note.py`
- **Done:** The SUMMARY's `Baseline decision:` line contains `refreshed` or `accepted` and two
  numeric `journal` pass_rate values; the check exits 0.
- **Criteria:** SC-11
- **Interfaces:** Consumes: the eval report from Task 4.1 and the pinned baseline. Produces: `specs/gh-166-list-trips-tool/SUMMARY.md`, `apps/api/scripts/check_gh166_baseline_note.py`.

## 5. Risks

| # | Risk | Mitigation |
|---|---|---|
| 1 | A hand-built projection leaves `date` objects in the payload and fails at JSON encoding | Project from `dump(trip)`; SC-7 asserts `json.dumps` succeeds |
| 2 | An implementer clones `get_trip_summary` mechanically and returns `_no_active_trip()` when `trip_id` is `None` | Stated in Global Constraints and in Task 1.1; a test covers the `trip_id=None` path |
| 3 | Prompt edits never reach the model (`active.yaml` not bumped; graph baked at lifespan startup) | Task 2.3's wiring script resolves through the registry; manual checks need `docker exec api-api-1 touch app/main.py` |
| 4 | The counting question routes to an agent with no trip tools, so the bug survives | Task 4.1 observes before deciding; no speculative supervisor bump |
| 5 | The eval gate trips on the `journal` capability rate | +1 golden only, existing naming case reused; Task 5.1 owns the explicit decision |
| 6 | `risk-corroboration.sh` blocks the commit on the public-contract signal | `Lane: high-risk` is already recorded in `SUMMARY.md` |
| 7 | Wave-2 tasks touch `active.yaml`, which Task 4.1 may touch again (different wave) | Different wave, so no parallel overlap; 4.1 edits a different key |
| 8 | Task 4.1's eval run is judged, paid, and container-only — not a gate | It is a manual step recorded under `### Not auto-verified`; the task's `Verify` checks only the recorded outcome |

## 6. Status Log

- 2026-09-09 — Plan written, then revised after an independent plan review: Task 1.2 retargeted to
  the real test file with the label pinned verbatim, `tools_expected` added to the updated golden,
  the new golden id pinned, Task 4.1's paid judged run demoted out of `Verify`, and the baseline
  task moved to its own wave (it consumed 4.1's output while sharing its wave). SC-9/10/11 added
  so Tasks 1.2, 4.1 and 5.1 stop borrowing criteria they do not satisfy. Intake (`SUMMARY.md`), design (approved, 2 review rounds), and Deep
  research brief complete. E001-A / E002-A(superseded) / E003-B recorded. Status: active — reviewed 3 rounds, approved.
