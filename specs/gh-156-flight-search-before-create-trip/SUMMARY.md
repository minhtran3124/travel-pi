<!--
  Canonical SUMMARY.md shape (templates/SUMMARY.template.md). Header block is machine-read:
  hooks/risk-corroboration.sh greps `Lane:`; the trust-metrics ledger reads Lane/Confidence/Flags.
-->

# gh-156-flight-search-before-create-trip — Summary

Lane: normal
Confidence: high
Reason: no manifest hard gate (the fix surface is the planner prompt + its pin test + CHANGELOG/active.yaml; no auth/authz/schema/route/provider/high-blast path). 2 flags fired: existing behavior (planner prompt bump v12 → v13 changes an LLM-decided tool order) and weak proof (nondeterministic — the exact failure reproduced in eval run 2 only; run 3 passed with the same unwanted `create_trip` still in the trace).
Flags: existing behavior, weak proof
Affects: apps/api/app/prompts/planner/* (+ active.yaml, CHANGELOG.md), apps/api/tests/prompts/test_planner_prompt.py; possibly the `create_trip` tool docstring in apps/api/app/tools/trip_tools.py (model-visible tool description)
Input-type: change request (bug #156, found by the review-b7 eval baseline)
Route: normal — using-git-worktrees (in-place branch `fix/gh-156-flight-search-before-create-trip` off `main`) → writing-plans (>2 files) → subagent-driven-development.
Escalate: no — one clear interpretation (the issue states the expected behavior: search first, do not create a trip for a bare search); the fix is prompt-level like the sibling #155/#146 fixes.

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> investigate cho issue https://github.com/minhtran3124/travel-pi/issues/156

Issue #156 (verbatim): "Found by the review-b7 full eval run 2 (2026-09-07, tier premium, authenticated). Turn 1 "Tôi muốn bay từ Hà Nội đi Phú Quốc", turn 2 "Ngày 25 tháng 3 năm 2027 nhé, cho 2 người lớn" → planner called `create_trip` and `resolve_date` but never `search_flights`; the oracle (5 offers, 123–751 USD) found no fare claim in the reply. In run 1 (anonymous context) the same golden was refused for a past date, so this surfaced only once trip creation was allowed. Expected: a flight *search* first; creating a trip is not what was asked. Spec: specs/review-b7-eval-baseline-ci/TRIAGE.md."

## What changed

Planner prompt bumped to **v13** (`apps/api/app/prompts/planner/v13.md`, `active.yaml` planner → 13, CHANGELOG entry): the "No active trip yet" flow and the Responsibilities / "How to Work" step-1 wording are gated on the traveller wanting to build or save an itinerary, and a new "Search first, save later" section says a find/compare/price request for flights, hotels, places or weather is a search that never needs a trip — run the search tool as soon as its required arguments are known, never call `create_trip` before a search, never open a trip the traveller did not ask for. The model-visible `create_trip` description (`apps/api/app/tools/trip_tools.py`) says the same. Both are pinned by content tests (`tests/prompts/test_planner_prompt.py`, `tests/tools/test_trip_tools.py`). The decision is recorded durably in `docs/solutions/agent/planner-search-first-save-later.md` (+ INDEX, critical-patterns).

Commits: b8c50b1 (create_trip docstring + pin), 3aaefdf (planner v13 + active.yaml + CHANGELOG + pin), ed7b630 (docs/solutions decision record), 5c6f574 (review fix: "as soon as you have its required arguments" instead of "straight away").

### Investigation (2026-09-08)

**Golden:** `apps/api/eval/datasets/flight_search.json` → `flight_search-multi_turn-vi-01`, `expected_flow: planner`, `expected_tools: [search_flights]`, oracle HAN→PQC 2027-03-25.

**Evidence across runs** (`specs/review-b7-eval-baseline-ci/TRIAGE.md`, `apps/api/eval/baselines/main.json`):
- run 1 (anonymous): refused — `create_trip` is refused for anonymous callers (#118), so the trip detour never got that far.
- run 2 (authenticated): `create_trip` + `resolve_date`, no `search_flights` → **fail** (this issue). Transcript not preserved, only tool names.
- run 3 (authenticated, committed baseline): tools called = `create_trip, get_trip_summary, resolve_date, search_flights` → **passes**, but the same detour is still there: the planner opens a trip the traveller never asked for before it searches. The pass is variance in whether the search happens after the detour, not the absence of the defect.

**Root cause (prompt-level, planner v12 — `apps/api/app/prompts/planner/v12.md`):**
- "Responsibilities": *"If there is no active trip yet, open one with `create_trip` before adding itinerary items … never ask the traveller for a trip id."*
- "How to Work" step 1: *"Use your tools to read the current trip and search real options … If there is no active trip, follow 'No active trip yet' first."* — this makes trip creation the first step of **every** planner turn with no active trip, including a bare flight search.
- "No active trip yet" section: triggers on *"the traveller wants to plan or add to an itinerary"* — a flight search is routed to planner by supervisor v11 ("Flight search … always routes to planner"), and the section does not say a search is exempt. Its step 2 says *"create the trip first, then add itinerary items in your next step"* — a two-round detour (resolve_date → create_trip → next round) that, in run 2, consumed the turn before `search_flights` ran.
- The `create_trip` tool docstring (`apps/api/app/tools/trip_tools.py:324`) reinforces it: *"Call this when there is no active trip, before shortlisting places or adding itinerary items."*
- Not the cause: `trip_guard` (`_base.py`) only blocks tools that inject `trip_id`; `search_flights` does not need a trip and is never blocked. `NO_ACTIVE_TRIP_MSG` says "offer to start a new trip … confirm before acting", which is the right behavior, but it only fires when a trip-scoped tool is attempted.

**Existing pin that constrains the fix:** `tests/prompts/test_planner_prompt.py::test_planner_prompt_keeps_create_trip_first_step` asserts the sentence *"create the trip first, then add itinerary items in your next step"* survives — the v13 edit must keep that sentence (it is about itinerary writes, which is fine) while scoping *when* the "No active trip yet" flow applies.

**Proposed fix direction (for writing-plans):**
1. planner **v13** (copy v12): scope "No active trip yet" + How to Work step 1 to *itinerary-writing* requests only; add an explicit rule: a pure search (flights / hotels / places / weather) never needs a trip — search first, answer with grounded options, and only offer to save/open a trip afterwards if the traveller wants to keep the result. Keep the pinned sentence verbatim.
2. Tighten the `create_trip` docstring the same way (model-visible; one file, no schema change).
3. Add a content pin in `tests/prompts/test_planner_prompt.py` for the new rule; CHANGELOG + `active.yaml` planner → 13.
4. Proof: `pytest tests/prompts tests/agents -x`, plus a narrowed eval run for the golden (`python -m eval --suite full --capability flight_search --language vi`, needs Docker db + `.env`) checking the trace has no `create_trip` and includes `search_flights`; k≥3 because of the variance noted above.

### Rationale

The defect is an instruction-ordering problem in the planner prompt, not a graph or tool bug: every code path (`trip_guard`, `search_flights`) already lets a trip-less search run. A prompt v13 + docstring change is the smallest fix and matches how #155/#146 were shipped.

### Alternatives considered

- Code guard that strips `create_trip` from the planner toolset until an itinerary write is requested — deterministic, but it would also block legitimate "plan my trip" turns and requires intent detection the supervisor does not emit today; keep as fallback if v13 does not hold at k=3.
- Route bare flight searches to a specialist without `create_trip` (concierge) — contradicts supervisor v11's "planner owns `search_flights`" rule and the #155 routing work; rejected.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| intake summary shape | `python .claude/scripts/verify_summary.py --lane gh-156-flight-search-before-create-trip` | 0 | intake | |
| planner v13 active + rule + pinned sentence | `cd apps/api && ../../.venv/bin/python -c "from app.prompts.registry import registry;assert registry.active_version('planner')==13;t=' '.join(registry.get('planner').split());assert 'Never call \`create_trip\` before a search' in t;assert 'create the trip first, then add itinerary items in your next step' in t"` | 0 | | SC-1 |
| planner prompt pin tests | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts/test_planner_prompt.py -q` | 0 | 3 passed | SC-2 |
| create_trip description says search first | `cd apps/api && ../../.venv/bin/python -c "from app.tools.trip_tools import create_trip as t;d=' '.join(t.description.split());assert 'Never call it for a search on its own' in d"` | 0 | | SC-3 |
| prompt suite + version snapshot + prompt map | `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts tests/agents/test_prompt_versions_snapshot.py tests/agents/test_prompt_map.py -q` | 0 | 48 passed | SC-4 |
| trip tool tests incl. description pin | `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_trip_tools.py -q` | 0 | 15 passed | SC-5 |
| narrowed judged eval (paid, >60s, Docker db + .env) | `<paid run, not re-run under --check: cd apps/api && ../../.venv/bin/python -m eval --suite full --capability flight_search --language vi --repeat 3 --out eval/reports/gh156-flight-vi.json>` | 0 | 3/3 pass; `flight_search-multi_turn-vi-01` tools called = `resolve_date, search_flights` (no `create_trip`); ran against v13 before commit 5c6f574's one-sentence wording change | |

### Not auto-verified

- run-2 failure mechanism (which round ended the turn) — reached traceability only; the eval run-2 transcript was not preserved, only the tool-name list in TRIAGE.md.
- the final wording of commit 5c6f574 ("as soon as you have its required arguments") — reached provenance (pin tests + SC-1 re-run); the paid eval ran against the pre-5c6f574 v13 text and was not re-run for a one-sentence change.
- goldens that expect `create_trip` for "plan my trip" phrasing keep passing — reached traceability only; not re-run (only the flight_search/vi slice was run).

### Advisory Findings

<!-- correctness-review (6 FIND angles → 1 deduplicated candidate → independent SCORE). Below threshold 75 = advisory, not fixed. -->

- **score 50 / P1 (guard-completeness)** — `apps/api/app/prompts/planner/v13.md:26` (+ Responsibilities bullet line 8): step 1 still opens with the combined default "read the current trip and search real options", with the bare-search exception only as a trailing clause. If the model batches `get_trip_summary` (trip-scoped) with `search_flights` while no trip is active, `trip_guard` (`_base.py`, unmodified) abandons the whole batch and ends the turn with "which trip?" — the search never runs. Scorer: mechanism is real and the baseline trace shows the model does call `get_trip_summary` on flight turns, but no trace shows the blocking path firing under v13 (both narrowed eval runs traced `resolve_date, search_flights` only). Suggested follow-up if it ever shows in eval: reword step 1 so "no active trip → for a bare search, search only; do not read the trip" comes before the default; or make `trip_guard` abandon only the trip-scoped calls in a batch (code change, separate spec).
- per-task review 1.2, Minor — `create_trip.description` is the whole docstring, so the reST `:param`/`:return` block ships to the model/MCP clients verbatim (pre-existing; every `@tool` in `trip_tools.py` is bare). Track separately if the noise matters.

### Intent Findings

<!-- intent-review (plan-blind, oracle = ### Intent verbatim). No gap, no drift. -->

- **excess (report-only)** — `docs/solutions/INDEX.md` churn from `.claude/scripts/rebuild_solution_index.py`: header rewording, row reorder, a previously-missing `rate-limit-build-vs-buy` row now indexed, and a bogus `## —` section listing `README.md` (the script excludes only `INDEX.md`/`critical-patterns.md`). Kept as the script's canonical output so `--check` stays consistent; the README row is a harness-script defect (see Harness-Delta).

### Rollback

- `git revert 5c6f574 ed7b630 3aaefdf b8c50b1` (prompt + docstring + tests + docs only); or set `active.yaml` `planner: 12` to restore the old prompt instantly

### Harness-Delta

- none
