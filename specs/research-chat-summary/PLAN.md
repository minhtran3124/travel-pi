---
slug: research-chat-summary
status: shipped
owner: minhtran3124
created: 2026-09-21
---

# research-chat-summary — a traveller-facing overview when trip research finishes

## 1. Motivation

When research finishes the chat only says "done". The traveller gets no overview of what was
found and has to open the Research tab to learn anything. See SUMMARY.md → Rationale.

## 2. Scope

In: the research agent writes `/research/summary.md` (short, traveller-facing, traveller's
language); the run is told the traveller's language; the chat launcher passes the chat language;
the chat "done" reply and the web research-done card show the summary.
Out: a separate summarizer call; persisting the summary as a chat message; the empty-proposal issue.

## Global Constraints

- The summary is written by the research agent in its final step — no new LLM call.
- The summary restates only facts already cited in the dimension files; it carries no tool tags or ids.
- Every run's input names the traveller's language; the chat launcher passes `state["language"]`.
- The FE reads the summary through the existing `GET /agent/research/{run_id}/files/summary.md`.
- A missing summary (older dossier, agent skipped it) degrades to today's card and reply, never an error.
- Minimal comments; one parameter per line for multi-param signatures.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|---|---|---|---|
| SC-1 | Run input carries a `Language:` line; chat launch passes the chat language | `cd apps/api && ../../.venv/bin/python -m pytest tests/research/test_runner.py -q` | exit 0 |
| SC-2 | trip_research v2 + dossier-format require `/research/summary.md` | `cd apps/api && ../../.venv/bin/python -m pytest tests/research/test_skills_prompts.py -q` | exit 0 |
| SC-3 | Chat "done" reply includes the summary when it exists, copy only when not | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_research_node.py -q` | exit 0 |
| SC-4 | Web card shows the summary; falls back without it | `cd apps/web && pnpm vitest run src/components/chat` | exit 0 |

## 4. Tasks

### Task 1.1 — Agent writes a summary in the traveller's language (wave 1)

- **Files:** apps/api/app/prompts/trip_research/v2.md, apps/api/app/prompts/active.yaml, apps/api/app/prompts/CHANGELOG.md, apps/api/app/research/skills/dossier-format/SKILL.md, apps/api/app/research/runner.py, apps/api/tests/research/test_runner.py, apps/api/tests/research/test_resume.py, apps/api/tests/research/test_skills_prompts.py
- **Action:** Copy v1 → v2: step 3 also writes `/research/summary.md`; write the dossier in the language named on the request's `Language:` line. Add summary.md to the dossier-format layout. `_build_input` appends `Language: <name>` to the turn message.
- **Criteria:** SC-1, SC-2
- **Interfaces:** Produces `v2.md`, `summary.md` contract in `SKILL.md`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/research/test_runner.py tests/research/test_skills_prompts.py -q`
- **Done:** both suites pass

### Task 1.2 — Chat launcher passes language and replies with the summary (wave 1)

- **Files:** apps/api/app/research/launcher.py, apps/api/app/research/service.py, apps/api/tests/agents/test_research_node.py
- **Action:** `launch(..., language=state language)`; on a completed run append the run's `summary.md` to the `research_completed` copy.
- **Criteria:** SC-1, SC-3
- **Interfaces:** Produces `ResearchService.completed_summary` in `service.py`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_research_node.py -q`
- **Done:** suite passes

### Task 2.1 — Card shows the summary (wave 2)

- **Files:** apps/web/src/components/chat/ResearchDoneCard.tsx, apps/web/src/components/chat/ResearchDoneCard.test.tsx, apps/web/messages/en.json, apps/web/messages/vi.json
- **Action:** Fetch `summary.md` for the done run and render it (markdown) above the chips; keep the hint line when absent.
- **Criteria:** SC-4
- **Interfaces:** Consumes `getResearchFile` in `apps/web/src/lib/api/research.ts`; produces `ResearchDoneCard.tsx`.
- **Verify:** `cd apps/web && pnpm vitest run src/components/chat`
- **Done:** tests pass

## 6. Status Log

- 2026-09-21 — tasks 1.1, 1.2, 2.1 complete
