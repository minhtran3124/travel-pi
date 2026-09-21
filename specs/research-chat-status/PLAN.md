---
slug: research-chat-status
status: shipped
owner: minhtran3124
created: 2026-09-21
---

# research-chat-status — tell the chat user when trip research is running or done

## 1. Motivation

After a chat-launched deep research run finishes, the chat never says so, and asking
"is my research done?" routes to the `research` launcher, which books another (empty) run,
spends the daily cap and replies "started" again. See SUMMARY.md → Rationale.

## 2. Scope

In: status-aware `research` chat node (A); supervisor v15 status-question rule + goldens (A);
web chat completion card for a run launched from chat (B).
Out: an LLM-written dossier summary; push from the runner into the chat thread; the empty
`proposal.json` quality issue (tracked separately).

## Global Constraints

- The launcher stays LLM-free; every reply is `system_reply(<key>, language)` copy.
- A chat turn on a trip whose latest run is `completed` or live `running` never calls `ResearchService.start`.
- `failed` / `interrupted` / orphaned `running` keep today's start/resume path.
- Every launcher reply is terminal for reflection (no REVISE back into the launcher).
- FE reads only the existing `GET /agent/trips/{trip_id}/research`; no new endpoint.
- Minimal comments; one parameter per line for multi-param signatures.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|---|---|---|---|
| SC-1 | Completed latest run → chat replies "done, see Research tab", no new run booked | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_research_node.py -q` | exit 0 |
| SC-2 | Live running run → chat replies "still researching", no new run booked | same as SC-1 | exit 0 |
| SC-3 | Status replies end the turn (reflection guard) | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_reflection_research_guard.py -q` | exit 0 |
| SC-4 | Supervisor v15 active with a status-question rule; en/vi goldens | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_supervisor_research_routing.py -q` | exit 0 |
| SC-5 | Web chat shows a completion card when a chat-launched run completes | `cd apps/web && pnpm vitest run src/components/chat` | exit 0 |

## 4. Tasks

### Task 1.1 — Status-aware research launcher (wave 1)

- **Files:** apps/api/app/research/launcher.py, apps/api/app/research/service.py, apps/api/app/agents/constants.py, apps/api/app/agents/copy.py, apps/api/app/agents/nodes.py, apps/api/tests/agents/test_research_node.py, apps/api/tests/agents/test_reflection_research_guard.py
- **Action:** Before `start`, read `service.latest(trip_id)` (owned by the caller). Live running → `research_in_progress`; completed → `research_completed`; else start as today. Mark status replies with `research_status` and let the reflection guard end on it.
- **Criteria:** SC-1, SC-2, SC-3
- **Interfaces:** Consumes `ResearchService.latest`; produces `RESEARCH_IN_PROGRESS_MSG`, `RESEARCH_COMPLETED_MSG` in `constants.py`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_research_node.py tests/agents/test_reflection_research_guard.py -q`
- **Done:** both suites pass

### Task 1.2 — Supervisor v15 status-question rule (wave 1)

- **Files:** apps/api/app/prompts/supervisor/v15.md, apps/api/app/prompts/active.yaml, apps/api/app/prompts/CHANGELOG.md, apps/api/eval/datasets/routing.json, apps/api/tests/eval/test_datasets.py, apps/api/tests/agents/test_supervisor_research_routing.py
- **Action:** Copy v14; Rule 6 also routes questions about the trip's deep research status/result to `research`; add en/vi examples and routing goldens; flip active.yaml.
- **Criteria:** SC-4
- **Interfaces:** Produces `v15.md`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_supervisor_research_routing.py tests/agents/test_prompt_map.py -q`
- **Done:** suites pass

### Task 2.1 — Chat completion card (wave 2)

- **Files:** apps/web/src/components/chat/useResearchWatch.ts, apps/web/src/components/chat/useResearchWatch.test.tsx, apps/web/src/components/chat/ResearchDoneCard.tsx, apps/web/src/components/chat/ResearchDoneCard.test.tsx, apps/web/src/components/chat/ChatPanel.tsx, apps/web/src/components/chat/ChatWidget.tsx, apps/web/src/components/chat/ChatWidget.test.tsx, apps/web/src/components/chat/useAgentStream.ts, apps/web/src/app/trips/[tripId]/page.tsx, apps/web/src/app/trips/[tripId]/page.test.tsx, apps/web/messages/en.json, apps/web/messages/vi.json
- **Action:** When a chat turn ends with `current_flow == "research"`, poll `GET /agent/trips/{id}/research` until terminal; on `completed` render a card (sections found, proposal ready, link to the Research tab).
- **Criteria:** SC-5
- **Interfaces:** Consumes `getLatestResearch` in `apps/web/src/lib/api/research.ts`; produces `ResearchDoneCard.tsx`.
- **Verify:** `cd apps/web && pnpm vitest run src/components/chat`
- **Done:** tests pass

## 6. Status Log

- 2026-09-21 — tasks 1.1, 1.2 complete; commit 0d362c5e
- 2026-09-21 — task 2.1 complete
