# research-proposal-validity — Summary

Lane: normal
Confidence: high
Reason: research-agent middleware + skill text, runner/service verdict read, one additive optional response field (`review`), chat copy and web card; no access-control change, no migration, no new endpoint.
Flags: none
Affects: app/research (agent middleware, skills, runner, service), research status response, apps/web chat card
Input-type: change request

### Intent

> vì sao chưa tạo dc proposal hợp lệ?

> ok, làm 1 + 2 trước

1 = research tools hand the model the ids the proposal needs (`place_id`, `offer_id`, `hotel_id`);
2 = a run whose grader never said `satisfied` is surfaced as "needs review" instead of "done".

## What changed

**1 — ids.** `_ToolIdsToContent` (research subagents only) appends an "Ids for the proposal"
list built from the `places` / `flights` / `hotels` artifact — `Name → place_id …`,
`VN1823 SGN→PQC … → offer_id …`, `Hotel → hotel_id …`. On the dev DB the real tools for Phu Quoc
now list ids, and `_unknown_ids` accepts them while rejecting `VN422` (what the live run wrote).
Skills: `flights` searches each leg one-way (a round-trip call lists outbound ids only) and never
uses a flight number as an offer id; `proposal` says where the ids are; `day-plans` no longer
tells the model `resolve_place` resolves names.

**2 — verdict.** After a completed stream the runner reads `_rubric_status` from the checkpoint
and writes a `rubric` step (`meta.rubric_status`; `rubric_status` added to the step meta
allowlist). `run_review` maps it to `review`: `passed` / `needs_review` / null, returned by both
status routes. `chat_state` returns `needs_review` for a rejected completed run (still never
re-run), with its own copy plus the summary; the web card shows an amber "a few gaps to check"
variant.

### Rationale

Live run `c5f09068` produced `{"itinerary": [], "shortlist": [], "flights": ["VN422", "OZ393"], "hotels": []}`:
the shared chat tools put ids only in the side-panel `artifact` — the model reads names, ratings and
flight numbers — so no prompt could make the proposal valid. The grader then failed it twice
(`RubricMiddleware exhausted max_iterations=2 without 'satisfied'`), yet the run finished
`completed` and the chat said "done". Ids are appended by a research-only middleware from the
artifact, so chat/MCP tool output stays byte-identical; the verdict is read from
`_rubric_status` on the checkpoint and recorded as a terminal step, keeping `status` values (and
the router's `_TERMINAL` set) unchanged.

### Alternatives considered

- Put ids in the shared tools' summaries — rejected: changes the chat's tool output (a shared prompt surface) and the MCP contract.
- New run status `needs_review` — rejected: every `status == "completed"` consumer and the SSE `_TERMINAL` loop would need changing.
- A new `agent_runs` column — rejected: migration for one flag; the step `meta` already carries terminal facts (`_error_step`).

### Deviations

- Rule 2 — `rubric_status` added to the step `meta` allowlist (`app/repositories/agent_run.py`); scalar enum, no text. Rule 1 — `day-plans` skill described `resolve_place` as a name lookup.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/research/test_tool_ids.py -q` | 0 | 9 passed; failed before the change (ImportError) | SC-1 |
| behavior | real `search_places` / `search_flights` / `browse_hotels` for Phu Quoc through the middleware in `api-api-1`, then `_unknown_ids` | 0 | ids listed; real ids valid, `VN422` rejected | |
| unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/research/test_runner.py tests/research/test_service.py -q` | 0 | rubric step for satisfied / max_iterations_reached; review mapping incl. null | SC-2 |
| unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_research_node.py -q` | 0 | needs_review copy + summary, no start | SC-3 |
| unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/research/test_routes.py -q` | 0 | both status routes return `review` | |
| unit (web) | `cd apps/web && pnpm vitest run src/components/chat` | 0 | 175 passed incl. needs-review variants en/vi | SC-4 |
| full BE suite | `pytest --rootdir apps/api -c apps/api/pyproject.toml apps/api/tests` from a cwd without `apps/api/.env` | 0 | 3003 passed, 9 skipped | |
| full web suite + typecheck + lint | `cd apps/web && pnpm vitest run && pnpm exec tsc --noEmit -p . && pnpm lint` | 0 | 393 passed; 0 lint errors (1 pre-existing warning) | |

### Not auto-verified

- A real run now writes a proposal with real ids — needs one paid run.

### Rollback

- `git revert <sha>`.

### Harness-Delta

- none
