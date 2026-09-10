# gh-173-supervisor-local-tips-fanout — Implementation Plan

Fix #173: the supervisor drops the `concierge` fan-out on a full trip-planning request that also
asks for local tips. Root cause (see `SUMMARY.md` → Intake findings): supervisor v11 §3 enumerates
the **planner's** tools by name but states the fan-out exception as a judgment call, so the
decidable half wins. The repair states both halves in tools.

Sibling constraint: **#149 is the opposite bug on the same decision** (`routing-multi-en-01`
"flights + weather" fans out when it should not). Every edit here must name weather and places as
planner-owned so it does not trade #173 green for #149 redder.

## 1. Global Constraints

- **Prompt-only.** No change to the graph, `route_tasks`, dedupe, HITL/booking detour, tier
  gating, or `TravelAgentState`. The only Python edit is a `Field(description=...)` string.
- **Every rule added must name a concrete tool.** No new judgment-shaped instruction
  ("genuinely independent", "if needed") — that is the defect being fixed.
- **The fan-out trigger list is exactly the concierge-exclusive tools** verified in
  `apps/api/app/tools/registry.py`: `get_local_tips`, `get_visa`, `search_travel_knowledge`.
  Do not add weather/places/climate/routing — the planner owns those (`#149` regression risk).
- **Version bump, never edit in place.** Copy `v11.md` → `v12.md`, edit `v12.md`, repoint
  `app/prompts/active.yaml`. `v11.md` stays byte-identical (`docs/solutions/agent/supervisor-active-yaml-is-a-pointer.md`).
- **The prompt and the schema description are read independently** (#156). Any carve-out added to
  the prompt is mirrored into `SupervisorIntent.plan`'s description.
- Prompt text is not hot-reloaded — a live check needs `docker exec api-api-1 touch app/main.py`
  (`docs/solutions/agent/langgraph-thread-reset-and-prompt-reload.md`). Not required for the
  offline suite or for `python -m eval`, which builds its own graph.
- Run backend commands from `apps/api/`; venv is `../../.venv`.

## 2. Scope

**In:** `apps/api/app/prompts/supervisor/v12.md` (new), `app/prompts/active.yaml`,
`app/prompts/CHANGELOG.md`, the `plan` field description in `app/agents/supervisor.py`,
`apps/api/tests/prompts/test_supervisor_prompt.py` (new),
`apps/api/eval/compare_capability.py` (new — the two-sided before/after comparison SC-8 runs;
`make eval-compare` answers a different question, whole-run vs the committed baseline at
capability level, so a single-capability pair needs its own check).

**Out:** the goldens in `eval/datasets/routing.json` (the oracle is correct — changing it was
rejected in `SUMMARY.md` → Alternatives); any code-level keyword fan-out; #149's own fix.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | The active supervisor prompt names all three concierge-exclusive tools as the fan-out trigger | `../../.venv/bin/python -m pytest tests/prompts/test_supervisor_prompt.py -q -k concierge_only_tools` | exit 0 |
| SC-2 | The active supervisor prompt states weather and places stay planner-owned (the #149 guard) | `../../.venv/bin/python -m pytest tests/prompts/test_supervisor_prompt.py -q -k planner_owned_not_a_trigger` | exit 0 |
| SC-3 | The Routing Examples block carries the contrastive pair — the same request with and without local tips | `../../.venv/bin/python -m pytest tests/prompts/test_supervisor_prompt.py -q -k contrastive_pair` | exit 0 |
| SC-4 | The model-visible `SupervisorIntent.plan` description carries the same carve-out | `../../.venv/bin/python -m pytest tests/prompts/test_supervisor_prompt.py -q -k plan_field_description` | exit 0 |
| SC-5 | `active.yaml` pins supervisor to a version whose file exists and loads nonempty | `../../.venv/bin/python -m pytest tests/prompts/test_active_versions_load.py tests/api/prompts/test_prompt_registry_helpers.py -q` | exit 0 |
| SC-6 | The supervisor's routing/dedupe/HITL behavior is unchanged by the edit | `../../.venv/bin/python -m pytest tests/agents/test_supervisor_plan_semantics.py tests/agents/test_multi_intent_routing.py tests/agents/test_plan_everything.py -q` | exit 0 |
| SC-7 | `v11.md` was not edited in place | `git diff --exit-code main -- app/prompts/supervisor/v11.md` | exit 0 |
| SC-8 | `routing-multi-en-04` passes and no other routing golden regresses, at k=3 | `../../.venv/bin/python eval/compare_capability.py eval/reports/gh173-before.json eval/reports/gh173-after.json` | exit 0 — exit 1 names any golden whose pass rate dropped |

> The paid eval run itself (>60s) is Task 4.1's `Verify`; SC-8's row is the cheap, re-runnable
> assertion **over the two reports it produces**, so the acceptance contract stays under 60s.

## 4. Tasks

### Task 1.1 — Supervisor v12: state the fan-out exception in tools (wave 1)

- **Files:** apps/api/app/prompts/supervisor/v12.md, apps/api/app/prompts/active.yaml, apps/api/app/prompts/CHANGELOG.md
- **Action:** Copy `v11.md` to `v12.md` unmodified, then make exactly three edits to `v12.md`:
  1. In `## Routing Rules` §3, keep the existing "chain inside ONE specialist's toolset" bullet
     verbatim, and add a second bullet stating the exception mechanically: local tips /
     etiquette (`get_local_tips`), visas and entry rules (`get_visa`) and general travel
     knowledge (`search_travel_knowledge`) have **no planner tool** and are concierge-only, so a
     trip-planning message that also asks for one of them is `target_agent=planner` **with**
     `plan=["concierge"]`. The same bullet must state that weather (`get_weather`) and places
     (`search_places`) are NOT triggers — the planner owns them, so "flights + weather" stays
     `plan=[]`. That sentence is the #149 guard; do not drop it.
  2. In `## Routing Examples`, directly beneath the existing
     `"plan my weekend: flights + a hotel + places to see + weather + a day-by-day itinerary"
     → planner alone (plan=[])` line, add its contrastive twin: the identical request **plus
     local tips** → `planner` with `plan=["concierge"]`, and say in the parenthetical that the
     only difference is the local-tips ask, which no planner tool answers. The pair must stay
     adjacent — the contrast is the teaching signal; a lone fan-out example only raises fan-out
     pressure.
  3. In `## Multi-step Plan`, on the bullet that begins "Omit any step a single specialist can do
     itself", append the converse: never omit a step the primary has no tool for, naming the same
     three concierge-only tools.
  Then set `supervisor: 12` in `active.yaml` and add a `## v12` entry at the top of the prompt
  `CHANGELOG.md` describing the change and citing #173 and #149.
- **Criteria:** SC-1, SC-2, SC-3, SC-5, SC-7
- **Interfaces:** Consumes `app/prompts/supervisor/v11.md` and the verified tool ownership in
  `app/tools/registry.py`. Produces `app/prompts/supervisor/v12.md`, an updated
  `app/prompts/active.yaml`, an updated `app/prompts/CHANGELOG.md`.
- **Verify:** `../../.venv/bin/python -m pytest tests/prompts/test_active_versions_load.py tests/api/prompts/test_prompt_registry_helpers.py -q`
- **Done:** `registry.get("supervisor")` returns the v12 text; `git diff main -- app/prompts/supervisor/v11.md` is empty; the three concierge-only tool names and the weather/places exclusion all appear in the active prompt.

### Task 1.2 — Mirror the carve-out into the `plan` field description (wave 1)

- **Files:** apps/api/app/agents/supervisor.py
- **Action:** In `SupervisorIntent.plan`'s `Field(description=...)`, keep every existing sentence
  and append the converse of "Omit any step that a single specialist can do itself": never omit a
  step the primary specialist has no tool for — local tips, visas and general travel knowledge are
  concierge-only, so a trip-planning message that also asks for one of them is
  `target_agent='planner'` with `plan=['concierge']`. This is a description string only: do not
  touch `_Target`, `_SecondaryTarget`, the dedupe logic, or any node.
- **Criteria:** SC-4, SC-6
- **Interfaces:** Consumes the wording agreed in Task 1.1. Produces an updated
  `app/agents/supervisor.py`.
- **Verify:** `../../.venv/bin/python -m pytest tests/agents/test_supervisor_plan_semantics.py -q`
- **Done:** The description mentions the concierge-only carve-out; `test_supervisor_plan_semantics.py` passes unchanged.

### Task 2.1 — Pin all four points with a content test (wave 2)

- **Files:** apps/api/tests/prompts/test_supervisor_prompt.py
- **Action:** Add a new content-pin module in the shape of `tests/prompts/test_planner_prompt.py`
  (read the active prompt via `registry.get("supervisor")`, normalize whitespace with
  `" ".join(text.split())` before substring assertions, since the prompt is hard-wrapped). Four
  tests, named so the `-k` selectors in the Success Criteria table resolve:
  `test_supervisor_prompt_names_concierge_only_tools` (all of `get_local_tips`, `get_visa`,
  `search_travel_knowledge` present),
  `test_supervisor_prompt_keeps_planner_owned_not_a_trigger` (`get_weather` and `search_places`
  are stated as staying with the planner),
  `test_supervisor_prompt_has_contrastive_pair` (both the planner-alone example and its
  local-tips twin are present, and the twin names `plan=["concierge"]`),
  `test_plan_field_description_carries_the_carve_out` (asserts on
  `SupervisorIntent.model_fields["plan"].description`, not the prompt).
  Assert on the rule's substance, never on a whole paragraph — a brittle full-paragraph pin
  breaks on the next legitimate bump.
- **Criteria:** SC-1, SC-2, SC-3, SC-4
- **Interfaces:** Consumes the v12 prompt and the updated field description. Produces
  `tests/prompts/test_supervisor_prompt.py`.
- **Verify:** `../../.venv/bin/python -m pytest tests/prompts/test_supervisor_prompt.py -q`
- **Done:** Four tests pass; each fails if its rule is deleted from the prompt (spot-check one by reverting it locally).

### Task 3.1 — Prove the agent workflow is unchanged (wave 3)

- **Files:** apps/api/tests/agents/test_supervisor_plan_semantics.py, apps/api/tests/agents/test_multi_intent_routing.py, apps/api/tests/agents/test_plan_everything.py
- **Action:** Run the three suites that own the supervisor's routing topology, dedupe, HITL
  booking detour and the flagship plan-everything path. Do not edit them — they are the
  regression oracle for "no workflow break". If one fails, the prompt edit reached beyond its
  declared scope: stop and report rather than adjusting the test.
- **Criteria:** SC-6
- **Interfaces:** Consumes the Wave 1–2 edits. Produces a pass/fail record for `SUMMARY.md` → `### Verify`.
- **Verify:** `../../.venv/bin/python -m pytest tests/agents/test_supervisor_plan_semantics.py tests/agents/test_multi_intent_routing.py tests/agents/test_plan_everything.py tests/agents/test_supervisor.py -q`
- **Done:** All four modules pass with zero edits to their source.

### Task 4.1 — Measure the routing capability at k=3, before vs after (wave 4)

- **Files:** apps/api/eval/reports/gh173-after.json, specs/gh-173-supervisor-local-tips-fanout/SUMMARY.md
- **Action:** With `docker compose up -d db` running and a real `OPENAI_API_KEY` in
  `apps/api/.env`, run the routing capability at k=3 and compare it case-by-case against
  `eval/reports/gh173-before.json` (captured on this branch before any edit). Record both
  per-case results in `SUMMARY.md` → `### Verify`. The ship gate is **two-sided**:
  `routing-multi-en-04` must improve, **and** `routing-multi-en-01`, `routing-multi-en-02`
  (planner-alone) and `routing-multi-en-03` (fan-out) must be no worse than the before run at the
  same k. If multi-en-04 goes green but a planner-alone golden goes red, the edit traded #173 for
  #149 — revert the contrastive example's wording and re-measure rather than shipping.
- **Criteria:** SC-8
- **Interfaces:** Consumes `eval/reports/gh173-before.json` and the v12 prompt. Produces
  `eval/reports/gh173-after.json` and the filled `### Verify` rows.
- **Verify:** `../../.venv/bin/python -m eval --suite full --capability routing --repeat 3 --out eval/reports/gh173-after.json --html eval/reports/gh173-after.html`
- **Done:** `gh173-after.json` exists; `routing-multi-en-04` passes at a higher rate than in `gh173-before.json`; no other routing golden's pass rate dropped.

### Task 5.1 — Reviewer round: close the independent review's findings (wave 5)

- **Files:** apps/api/app/prompts/supervisor/v12.md, apps/api/tests/prompts/test_supervisor_prompt.py, specs/gh-173-supervisor-local-tips-fanout/PLAN.md
- **Action:** Close the three findings the independent reviewer raised against the Wave 1–2 diff.
  (1) v12 still carried three unqualified collapse-to-one instructions that out-rank the new
  rule by the plan's own thesis — Routing Rule 1 ("Choose **exactly one** sub-agent"), and the
  `## Multi-step Plan` intro's judgment-shaped gate. Qualify Rule 1 so "exactly one" scopes to
  `target_agent` and points at Rule 3 for the `plan` decision, and anchor the Multi-step intro's
  "cannot cover" to Rule 3's tool list. (2) "Exactly three asks" was a closed list that would
  silently exclude the next concierge-only tool — reopen it ("an ask the primary has no tool
  for", with the three as today's members). (3) Two of the four pin tests asserted verbatim
  ~20-word prompt sentences, the brittleness Task 2.1 forbade — re-assert on substance, and
  prove each rewritten pin still fails when its rule is actually absent.
  Do not add fan-out pressure: every edit here either scopes an existing over-broad rule or
  points at Rule 3, which already names weather and places as planner-owned.
- **Criteria:** SC-1, SC-2, SC-3, SC-8
- **Interfaces:** Consumes the independent review of the Wave 1–2 staged diff. Produces the
  revised `app/prompts/supervisor/v12.md` and `tests/prompts/test_supervisor_prompt.py`.
- **Verify:** `../../.venv/bin/python -m pytest tests/prompts/test_supervisor_prompt.py tests/agents/test_supervisor_plan_semantics.py -q`
- **Done:** The four pins pass, and each of the two rewritten pins was shown to fail with its rule removed and pass with it restored. The routing capability is re-measured after these edits (Task 4.1 re-run) because the prompt changed again.

## 5. Rollback

- `git revert <sha>` per commit, or repoint `app/prompts/active.yaml` back to `supervisor: 11` for
  an immediate prompt-level revert with no code change.
