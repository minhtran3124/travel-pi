---
slug: research-dossier-reader
status: shipped
owner: minhtran3124
created: 2026-09-22
---

# research-dossier-reader — traveller-facing dossier: no ids or tool names, their language

## 1. Motivation

Run `0f71586a` (Đà Nẵng) passed the grader with real ids, but the files the traveller reads are full
of `(search_flights)` tags and `offer_id \`…\``, and the dimension files are in English while the
traveller writes Vietnamese — subagents never see the `Language:` line.

## 2. Scope

In: a reader view on the traveller-facing file reads (route + chat summary); ids moved to a trailing
`## Ids` section; a subagent language middleware; grader v2 criterion 5 per file. Out: localized
file names in the tab's file list.

## Global Constraints

- The stored dossier keeps its citations and ids (grader + proposal assembly need them).
- The reader view is a pure function on text; the agent, grader and proposal never read it.
- Language comes from `state["language"]`; no model call to translate.
- Minimal comments; one parameter per line for multi-param signatures.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|---|---|---|---|
| SC-1 | Reader view strips tool tags, ids and the `## Ids` section from real dossier text | `cd apps/api && ../../.venv/bin/python -m pytest tests/research/test_reader.py -q` | exit 0 |
| SC-2 | File route and chat summary serve the reader view | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/research/test_routes.py tests/agents/test_research_node.py -q` | exit 0 |
| SC-3 | Every subagent model call carries the traveller's language | `cd apps/api && ../../.venv/bin/python -m pytest tests/research/test_language.py -q` | exit 0 |
| SC-4 | Skills + grader v2 require ids in `## Ids` and per-file language | `cd apps/api && ../../.venv/bin/python -m pytest tests/research/test_skills_prompts.py -q` | exit 0 |

## 4. Tasks

### Task 1.1 — Reader view (wave 1)

- **Files:** apps/api/app/research/reader.py, apps/api/app/research/service.py, apps/api/app/routers/research.py, apps/api/tests/research/test_reader.py, apps/api/tests/api/research/test_routes.py, apps/api/tests/agents/test_research_node.py
- **Action:** `reader_view(text)`; the files GET route and `completed_summary` return it; PUT unchanged.
- **Criteria:** SC-1, SC-2
- **Interfaces:** Produces `reader_view` in `reader.py`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/research/test_reader.py tests/api/research/test_routes.py -q`
- **Done:** suites pass

### Task 1.2 — Language for subagents; ids section; grader v2 (wave 1)

- **Files:** apps/api/app/research/agent.py, apps/api/app/research/skills/dossier-format/SKILL.md, apps/api/app/research/skills/flights/SKILL.md, apps/api/app/research/skills/stays/SKILL.md, apps/api/app/research/skills/day-plans/SKILL.md, apps/api/app/research/skills/proposal/SKILL.md, apps/api/app/prompts/trip_research_grader/v2.md, apps/api/app/prompts/active.yaml, apps/api/app/prompts/CHANGELOG.md, apps/api/tests/research/test_language.py, apps/api/tests/research/test_skills_prompts.py
- **Action:** `_WriteInTravellerLanguage` model middleware on subagents and the main agent; skills put ids only in a trailing `## Ids` section and never name tools in prose; grader v2 fails an off-language file.
- **Criteria:** SC-3, SC-4
- **Interfaces:** Produces `_WriteInTravellerLanguage` in `agent.py`, `trip_research_grader/v2.md`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/research/test_language.py tests/research/test_skills_prompts.py -q`
- **Done:** suites pass

## 6. Status Log

- 2026-09-22 — tasks 1.1, 1.2 complete
