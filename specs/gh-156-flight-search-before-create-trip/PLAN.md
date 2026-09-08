---
slug: gh-156-flight-search-before-create-trip
status: shipped
owner: Minh Tran
created: 2026-09-08
---

# Planner: search flights first, never open a trip for a bare search (#156)

## 1. Motivation

Golden `flight_search-multi_turn-vi-01` ("Tôi muốn bay từ Hà Nội đi Phú Quốc" → "Ngày 25 tháng 3 năm 2027 nhé, cho 2 người lớn") made the planner call `create_trip` + `resolve_date` and never `search_flights` (eval run 2); the committed baseline (run 3) still shows `create_trip` before `search_flights`. Planner v12 makes trip creation the first step of every turn with no active trip, and the `create_trip` docstring says the same, so a bare flight search is treated as "plan a trip". Investigation: `SUMMARY.md`; research: `research-brief.md`.

## 2. Non-goals

- No change to the graph (`_base.py`, `trip_guard`), the tool registry, or supervisor routing.
- No removal of `create_trip` from the planner toolset.
- No golden or eval-code edits; the paid eval run is phase-level acceptance, not a task Verify.
- No edits to any `apps/api/app/**` file other than `app/prompts/planner/v13.md`, `app/prompts/active.yaml`, `app/prompts/CHANGELOG.md`, and the `create_trip` docstring in `app/tools/trip_tools.py`.

## Global Constraints

- Branch `fix/gh-156-flight-search-before-create-trip` off `main` (in-place, created by `using-git-worktrees`); run backend commands from `apps/api/` with `../../.venv/bin/python`.
- Prompt bump convention: copy `v12.md` → `v13.md`, edit only the lines named in Task 1.1, point `active.yaml` `planner: 13`, prepend a CHANGELOG entry headed `## gh-156-flight-search-before-create-trip — …`. The sentence `create the trip first, then add itinerary items in your next step` stays verbatim (pinned by `tests/prompts/test_planner_prompt.py`).
- Tests first: write the failing pin test, then make the prompt/docstring edit.
- Same-wave tasks never share a file. Stage and commit as separate commands; no tooling trailers in commit messages. Lane normal: per-task review on.
- A live check needs a graph rebuild (`docker exec api-api-1 touch app/main.py`); prompt files are not hot-reloaded.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | Planner v13 is the active prompt, states the search-first rule, and keeps the pinned create-then-add sentence | `cd apps/api && ../../.venv/bin/python -c "from app.prompts.registry import registry;assert registry.active_version('planner')==13;t=' '.join(registry.get('planner').split());assert 'Never call \`create_trip\` before a search' in t;assert 'create the trip first, then add itinerary items in your next step' in t"` | exit 0 |
| SC-2 | The planner prompt pin tests (v12 batching + v13 search-first) pass | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts/test_planner_prompt.py -q` | exit 0 |
| SC-3 | The model-visible `create_trip` description tells the model to search first and never open a trip for a bare search | `cd apps/api && ../../.venv/bin/python -c "from app.tools.trip_tools import create_trip as t;d=' '.join(t.description.split());assert 'Never call it for a search on its own' in d"` | exit 0 |
| SC-4 | Every active prompt version still loads and the version snapshot / registry tests pass | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts tests/agents/test_prompt_versions_snapshot.py tests/agents/test_prompt_map.py -q` | exit 0 |
| SC-5 | Trip-tool tests (incl. the new description pin) pass | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_trip_tools.py -q` | exit 0 |

The full BE suite (`pytest tests/`, ~3 min) and the keyed eval run (`python -m eval --suite full --capability flight_search --language vi --repeat 3`) run at `finishing-a-development-branch` / phase acceptance, not in a task Verify.

## 4. Tasks

### Task 1.1 — Planner prompt v13: search first, save later (wave 1)

- **Files:** apps/api/app/prompts/planner/v13.md, apps/api/app/prompts/active.yaml, apps/api/app/prompts/CHANGELOG.md, apps/api/tests/prompts/test_planner_prompt.py
- **Action:** Test first: in `tests/prompts/test_planner_prompt.py` add `test_planner_prompt_searches_before_creating_a_trip` asserting the whitespace-normalized active planner text contains `Never call \`create_trip\` before a search` and `Search first, save later`; update the module docstring to mention v13. Run it and confirm it fails. Then copy `v12.md` to `v13.md` and make exactly these edits: (a) Responsibilities bullet (v12 lines 9–10) becomes "If the traveller wants to build or save an itinerary and there is no active trip yet, open one with `create_trip` before adding itinerary items (see "No active trip yet") — never ask the traveller for a trip id. A search on its own never needs a trip (see "Search first, save later")." (b) "How to Work" step 1 second sentence (v12 line 25) becomes "If there is no active trip and the traveller is asking you to build or add to an itinerary, follow "No active trip yet" first; for a search on its own, search first (see "Search first, save later")." (c) "No active trip yet" opening sentence (v12 line 39) "wants to plan or add to an itinerary" → "wants to build, add to, or save an itinerary (not merely search — see "Search first, save later")". (d) Insert a new section after "No active trip yet" and before "Ask only for what's missing", headed `## Search first, save later`, with this body: "A request to find, compare, or price flights, hotels, places, or weather is a **search**, not a trip. Run the search tool straight away (`search_flights`, `search_hotels`, `search_places`, …) — none of them needs an active trip — and answer with the grounded options. **Never call `create_trip` before a search**, and never open a trip the traveller did not ask for. The trip only needs to exist once they choose an option and want to keep it ("add it to my trip", "save this", "plan the rest of the days") — then follow "No active trip yet"." No other v12 line changes; the pinned sentence in step 2 of "No active trip yet" stays verbatim. Set `active.yaml` `planner: 12` → `13`. Prepend a CHANGELOG entry headed `## gh-156-flight-search-before-create-trip — planner searches first; a bare search never opens a trip` with one bullet for planner v13 (copied v12; the four edits above) and one for the code half (`create_trip` docstring, Task 1.2), closing with `` `active.yaml`: planner → 13 ``.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts/test_planner_prompt.py tests/prompts/test_active_versions_load.py -q`
- **Done:** the three pin tests pass; `diff app/prompts/planner/v12.md app/prompts/planner/v13.md` shows only the four hunks (a)–(d); `active.yaml` reads `planner: 13`; the CHANGELOG entry is the first `## ` heading in the file.
- **Criteria:** SC-1, SC-2, SC-4
- **Interfaces:** Consumes the prompt registry pointer convention (active.yaml) and the existing planner v12 text. Produces `apps/api/app/prompts/planner/v13.md`, `apps/api/app/prompts/active.yaml` (planner → 13), `apps/api/app/prompts/CHANGELOG.md` (entry), `apps/api/tests/prompts/test_planner_prompt.py` (v13 pin).

### Task 1.2 — `create_trip` docstring: search tools never need a trip (wave 1)

- **Files:** apps/api/app/tools/trip_tools.py, apps/api/tests/tools/test_trip_tools.py
- **Action:** Test first: in `tests/tools/test_trip_tools.py` add `test_create_trip_description_says_search_first` asserting the whitespace-normalized `create_trip.description` contains `Never call it for a search on its own`. Run it and confirm it fails. Then edit only the docstring summary paragraph of `create_trip` (`app/tools/trip_tools.py` lines 346–348, "Call this when there is no active trip, before shortlisting places or adding itinerary items.") to read: "Call this only when the traveller wants to build or save an itinerary and there is no active trip yet — before shortlisting places or adding itinerary items. Never call it for a search on its own (flights, hotels, places): the search tools do not need a trip, so search first and open a trip only once the traveller wants to keep a result." Leave the `:param` block, the `Command` body, and the MCP-visible signature untouched.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_trip_tools.py -q`
- **Done:** the new test passes with the rest of the file; `git diff --stat app/tools/trip_tools.py` reports one file with only docstring lines changed; `ruff check app/tools/trip_tools.py tests/tools/test_trip_tools.py` reports 0 findings.
- **Criteria:** SC-3, SC-5
- **Interfaces:** Consumes the tool decorator's docstring-as-description exposure, which is what the planner model and MCP clients read. Produces `apps/api/app/tools/trip_tools.py` (docstring), `apps/api/tests/tools/test_trip_tools.py` (description pin).

## 5. Risks

- Prompt compliance is probabilistic: the v13 rule may still be ignored on some runs. Mitigation: the phase-level keyed eval run at k=3 (`--capability flight_search --language vi`), checking the per-case `tools_expected.detail` contains `search_flights` and not `create_trip`; if it does not hold, fall back to the code-guard alternative in `SUMMARY.md`.
- MCP clients also read the `create_trip` description; the wording change is additive guidance, no schema change.
- Existing goldens that expect `create_trip` for "plan my trip" phrasing must keep passing; the edits only scope the rule to itinerary-writing intent and never remove the tool.

## 6. Status Log

- 2026-09-08 — plan written (intake normal / high confidence); branch `fix/gh-156-flight-search-before-create-trip` created off `main`; baseline `pytest tests/prompts tests/agents` 420 passed.
- 2026-09-08 — tasks 1.1, 1.2 complete; commits 3aaefdf, b8c50b1 (verify green; per-task reviews dispatched)
- 2026-09-08 — per-task reviews 1.1, 1.2: spec pass / quality approved; 1.1 Minor (hotel "straight away" tension) fixed in 5th commit; 1.2 Minor (pre-existing reST noise in create_trip description) recorded, no change
- 2026-09-08 — final chain: correctness-review 6 angles → 1 candidate scored 50 (advisory, recorded); intent-review no gap/drift, 1 excess report-only (INDEX churn); narrowed eval flight_search/vi k=3 3/3 pass twice (trace resolve_date → search_flights). Ready for finishing-a-development-branch.
