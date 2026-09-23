---
slug: research-review-fixes
status: shipped
owner: minhtran3124
created: 2026-09-23
---

# research-review-fixes — act on the PR #221 code review

## 1. Motivation

The multi-agent review of PR #221 confirmed 16 findings. Eight small fixes were applied during the
review. The owner then decided the remaining design questions
(https://claude.ai/artifact/CHp1TeQ5twSYNHYAVzEHVV):

| # | Decision |
|---|----------|
| D1 | Deferred to after merge — issue #225 (v3 progress stream) |
| D2 | A — a failed/interrupted run shows "not finished", Apply hidden, files still readable |
| D3 | B — a cancelled run is not finalized; the row stays `running` so the next start resumes it |
| D4 | A — the chat plan panel locks Apply ("Updating…") while a newer run is running |
| D5 | A — status reads a `running` row that is not live on the bus as `interrupted` (display only) |
| D6 | Deferred — issue #226 (ORM behind repositories/) |
| D7 | A — no change; revise stays in the Research tab |

## 2. Scope

In: D2, D3, D4, D5; tests for the PUT files route (#3) and `chat_state` (#13).
Out: D1 (#225), D6 (#226), D7.

## 3. Tasks

### Wave 1 (parallel, disjoint files)

- **T1 backend** — Files: `apps/api/app/research/runner.py`, `apps/api/app/routers/research.py`,
  `apps/api/tests/research/test_runner.py`, `apps/api/tests/api/research/test_routes.py`,
  `apps/api/tests/research/test_service.py`.
  D3: on `CancelledError` skip `repo.finish` (row stays `running`), close the bus channel, re-raise.
  D5: `_status_body` reports `interrupted` for a `running` row not live on the bus; `proposal_ready`
  false unless the run is `completed` (D2 backend half). Tests: PUT files owner/foreign, `chat_state`
  live vs not-live, D3, D5.
  Verify: `pytest tests/research tests/api/research tests/streaming tests/agents/test_research_node.py`.
- **T2 frontend** — Files: `apps/web/src/components/trips/research/ResearchTab.tsx`,
  `ResearchPlan.tsx`, `ResearchPlan.test.tsx`, `ResearchTab.test.tsx`,
  `apps/web/src/components/chat/useResearchWatch.ts` (+ test), `ChatWidget.tsx`,
  `apps/web/src/components/chat/panel/ResearchPlanPanel.tsx` (+ test), `apps/web/messages/{en,vi}.json`.
  D2: status-aware plan view. D4: lock Apply in the chat panel while a newer run is running.
  Verify: `pnpm vitest run`, `pnpm lint`, `pnpm tsc --noEmit`.

## 4. Verification

Full backend suite in a clean worktree (the main checkout's `.env` causes about 59 unrelated failures) and
the full frontend suite.

## 5. Status Log

- 2026-09-23 — tasks T1, T2 complete (with the in-review fixes); commit 097f4bed
