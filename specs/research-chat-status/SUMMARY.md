# research-chat-status — Summary

Lane: normal
Confidence: high
Reason: agent-behaviour change (research launcher + supervisor prompt v15) and a web chat card; no auth, schema, migration or new endpoint — the FE reads the existing GET /agent/trips/{id}/research.
Flags: none
Affects: app/research/launcher.py, supervisor prompt, apps/web chat widget
Input-type: change request

### Intent

> hiện tại có vẻ việc research đã xong, nhưng ko hiện thông báo hoàn tất ở chatbot, cũng ko có 1 summary nào cả. Việc này sẽ khiến user ko biết dc

> làm A trước xong rồi B

A = the chat `research` node answers from the trip's latest run (running → in progress,
completed → done + pointer to the Research tab) instead of always booking a new run.
B = the web chat notices when a research run it launched completes and shows a completion
card with a short summary and a link to the Research tab.

## What changed

**Wave 1 (A):** `ResearchService.chat_state` reports the caller's latest run for the trip
(`running` only when live on this process's bus, `completed`); the chat `research` node replies
`research_in_progress` / `research_completed` for those instead of calling `start`, marked
`research_status` so reflection ends the turn. `failed` / `interrupted` / orphaned `running`
keep the start/resume path. Supervisor v15 routes research status questions to `research`;
goldens `research-status-{en,vi}-01` (dataset count 115 → 117). Commit `0d362c5e`.

**Wave 2 (B):** `onTurnComplete` now receives the turn's `current_flow`; after a `research`
turn the chat widget follows the trip's latest run (`useResearchWatch`, polling
`GET /agent/trips/{id}/research` every 5 s while `running`; also on mount, so a reload mid-run
is followed). When a run it saw running completes, `ResearchDoneCard` shows above the composer:
the dossier sections from the file index (N-day plan, flights, stays, entry & season, budget),
"proposal ready", and a link to `/trips/{id}?tab=research`. The trip page now honours `?tab=`
(unknown/disabled tab falls back to itinerary). Summary is structural and FE-i18n (en/vi) — no
LLM prose.

### Rationale

A status question ("bạn chạy research xong chưa?") routed to `research` and booked a new run
(`aa59c297`, 5 s, empty revise turn), spending the last of the 3/day cap and replying "started"
again. The chat launcher passes no instruction, so a chat re-run on a completed dossier is an
empty revise — status-aware replies fix the wasted run and the missing "done" signal together,
deterministically, without a supervisor schema change.

### Alternatives considered

- New `SupervisorIntent` field (start vs status) — rejected: widens the structured-output contract for every turn; the node already has the ground truth (run status).
- Push a completion message into the chat thread from the runner — rejected: the run does not know the chat conversation_id; FE polling of an existing endpoint is additive.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_research_node.py -q` | 0 | completed + running cases; failed before the change (ImportError) | SC-1 |
| unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_research_node.py -q` | 0 | running (live) case books nothing | SC-2 |
| unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_reflection_research_guard.py -q` | 0 | `research_status` ends reflection | SC-3 |
| unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_supervisor_research_routing.py tests/eval/test_datasets.py -q` | 0 | v15 status rule + 117 goldens | SC-4 |
| full BE suite | `pytest --rootdir apps/api -c apps/api/pyproject.toml apps/api/tests` from a cwd without `apps/api/.env` | 0 | 2978 passed, 9 skipped (from `apps/api/` the real `.env` reddens 59 unrelated tests, same on baseline) | |
| lint | `cd apps/api && ruff check app scripts` | 0 | | |
| unit (web) | `cd apps/web && pnpm vitest run src/components/chat` | 0 | 174 passed incl. useResearchWatch (7), ResearchDoneCard (6), ChatWidget research (2) | SC-5 |
| unit (web) | `cd apps/web && pnpm vitest run src/app/trips` | 0 | `?tab=research` opens the tab; disabled falls back | |
| typecheck + lint (web) | `cd apps/web && pnpm exec tsc --noEmit -p . && pnpm lint` | 0 | 0 errors; 1 pre-existing warning (useAgentStream `t` dep, on baseline) | |
| build (web) | `cd apps/web && pnpm build` | 0 | full web suite also 388 passed | |

### Not auto-verified

- A real model routes status questions to `research` under v15 — goldens added, keyed eval not run (paid).
- Browser UAT of the completion card against a real run — not run: the test user spent today's 3/3 research runs.
- The dossier from the UAT run had an empty `proposal.json` (itinerary/flights/hotels `[]`) — research-agent quality issue, out of scope here.

### Rollback

- `git revert <sha>` per wave commit.

### Harness-Delta

- none
