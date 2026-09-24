---
slug: research-proposal-validity
status: shipped
owner: minhtran3124
created: 2026-09-22
---

# research-proposal-validity — ids the model can cite, and an honest verdict

## 1. Motivation

A live run could not produce a valid proposal: the model never sees the ids, and a run the grader
rejected is reported as done. See SUMMARY.md → Rationale.

## 2. Scope

In: research-only middleware appending ids from panel artifacts; skill text on ids and one-way
legs; the grader verdict recorded per run and shown in the chat reply, the chat card and the status
response. Out: trip origin handling in the flights skill (item 3); seed inventory (item 4).

## Global Constraints

- Shared tools, the chat graph and the MCP surface stay byte-identical (research-only middleware).
- `agent_runs.status` values are unchanged; the verdict is a terminal step's `meta`.
- `review` is an optional additive field: `"passed" | "needs_review" | null` (null = not graded).
- A `needs_review` run is still finished: the chat never re-runs it on its own.
- Minimal comments; one parameter per line for multi-param signatures.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|---|---|---|---|
| SC-1 | Places/flights/hotels tool results carry their ids for the research model only | `cd apps/api && ../../.venv/bin/python -m pytest tests/research/test_tool_ids.py -q` | exit 0 |
| SC-2 | A run's grader verdict is recorded and returned as `review` | `cd apps/api && ../../.venv/bin/python -m pytest tests/research/test_runner.py tests/research/test_service.py -q` | exit 0 |
| SC-3 | Chat says "needs review" for a rejected run and never restarts it | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_research_node.py -q` | exit 0 |
| SC-4 | Web card shows the needs-review variant | `cd apps/web && pnpm vitest run src/components/chat` | exit 0 |

## 4. Tasks

### Task 1.1 — Ids into the research model's tool results (wave 1)

- **Files:** apps/api/app/research/agent.py, apps/api/app/research/skills/proposal/SKILL.md, apps/api/app/research/skills/flights/SKILL.md, apps/api/app/research/skills/day-plans/SKILL.md, apps/api/tests/research/test_tool_ids.py
- **Action:** `_ToolIdsToContent` middleware (sync + async) appends an "Ids" block built from a `places` / `flights` / `hotels` artifact; bind it on every subagent. Skills: the proposal's id formats; flights searches each leg one-way.
- **Criteria:** SC-1
- **Interfaces:** Produces `_ToolIdsToContent` in `agent.py`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/research/test_tool_ids.py -q`
- **Done:** suite passes

### Task 1.2 — Record and expose the grader verdict (wave 1)

- **Files:** apps/api/app/research/runner.py, apps/api/app/research/service.py, apps/api/app/research/launcher.py, apps/api/app/agents/constants.py, apps/api/app/agents/copy.py, apps/api/app/schemas/research.py, apps/api/app/routers/research.py, apps/api/app/repositories/agent_run.py, apps/api/tests/api/research/test_routes.py, apps/api/tests/research/test_runner.py, apps/api/tests/research/test_service.py, apps/api/tests/agents/test_research_node.py
- **Action:** Runner reads `_rubric_status` after a completed stream and adds a `rubric` step with `meta.rubric_status`. Service `review(run)` maps it; status response gains `review`; chat_state returns `needs_review` for a rejected completed run with its own copy.
- **Criteria:** SC-2, SC-3
- **Interfaces:** Produces `ResearchService.review` in `service.py`, `RESEARCH_NEEDS_REVIEW_MSG` in `constants.py`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/research/test_runner.py tests/research/test_service.py tests/agents/test_research_node.py -q`
- **Done:** suites pass

### Task 2.1 — Card needs-review variant (wave 2)

- **Files:** apps/web/src/lib/api/research.ts, apps/web/src/components/chat/ResearchDoneCard.tsx, apps/web/src/components/chat/ResearchDoneCard.test.tsx, apps/web/messages/en.json, apps/web/messages/vi.json
- **Action:** `ResearchRunSummary.review`; the card's title/hint switch to a gentle "a few gaps to check" variant when `review === "needs_review"`.
- **Criteria:** SC-4
- **Interfaces:** Consumes `review` from `GET /agent/trips/{id}/research`; produces `ResearchDoneCard.tsx`.
- **Verify:** `cd apps/web && pnpm vitest run src/components/chat`
- **Done:** tests pass

## 6. Status Log

- 2026-09-22 — tasks 1.1, 1.2, 2.1 complete
