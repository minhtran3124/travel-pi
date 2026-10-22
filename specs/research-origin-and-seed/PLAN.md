---
slug: research-origin-and-seed
status: shipped
owner: minhtran3124
created: 2026-09-22
---

# research-origin-and-seed — ask for the departure point; enough Phu Quoc inventory

## 1. Motivation

A live run invented a route (DNA→DAD) because the trip has no departure point, and Phu Quoc's
seed inventory (3 hotels, all 5★ from USD 195; no restaurants or cafes) cannot satisfy a
budget traveller. See SUMMARY.md → Rationale.

## 2. Scope

In: the chat asks for the origin before launching research and never launches without one; the
run carries it (`Departing from:` line); the Research tab's Start asks for it; the flights skill
never searches without it. Phu Quoc seed: budget + mid hotels, restaurants and cafes (en + vi).
Out: a persisted trip origin column; origin for revise turns (the thread already carries it).

## Global Constraints

- Never assume a departure point: no default, no inference from the destination or profile.
- The launcher stays LLM-free; the origin comes from `trip_facts.origin` (supervisor slot).
- `ResearchStartRequest.origin` is optional and additive; the web Start requires it.
- Seed rows are deterministic (same id scheme as existing rows); existing rows are unchanged.
- Minimal comments; one parameter per line for multi-param signatures.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|---|---|---|---|
| SC-1 | Chat without a known origin asks for it and books no run | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_research_node.py -q` | exit 0 |
| SC-2 | The run input names the origin; REST start passes it | `cd apps/api && ../../.venv/bin/python -m pytest tests/research/test_runner.py tests/api/research/test_routes.py -q` | exit 0 |
| SC-3 | Supervisor v15 routes an answer to research's origin question back to research | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_supervisor_research_routing.py -q` | exit 0 |
| SC-4 | Research tab Start requires an origin | `cd apps/web && pnpm vitest run src/components/trips/research` | exit 0 |
| SC-5 | Phu Quoc has budget/mid hotels and restaurants/cafes with vi translations | `cd apps/api && ../../.venv/bin/python -m pytest tests/data -q` | exit 0 |

## 4. Tasks

### Task 1.1 — Ask for the origin and carry it into the run (wave 1)

- **Files:** apps/api/app/research/launcher.py, apps/api/app/research/service.py, apps/api/app/research/context.py, apps/api/app/research/runner.py, apps/api/app/research/skills/flights/SKILL.md, apps/api/app/agents/constants.py, apps/api/app/agents/copy.py, apps/api/app/prompts/supervisor/v15.md, apps/api/app/prompts/CHANGELOG.md, apps/api/app/schemas/research.py, apps/api/app/routers/research.py, apps/api/tests/agents/test_research_node.py, apps/api/tests/agents/test_supervisor_research_routing.py, apps/api/tests/research/test_runner.py, apps/api/tests/api/research/test_routes.py
- **Action:** Launcher: no `trip_facts.origin` → `research_needs_origin` + `awaiting_user`, no start; else `launch(..., origin=)`. `ResearchContext.origin`; `_build_input` adds `Departing from:`. REST body `origin`. Flights skill: origin only from that line. Supervisor v15: the answer to that question routes to research.
- **Criteria:** SC-1, SC-2, SC-3
- **Interfaces:** Produces `RESEARCH_NEEDS_ORIGIN_MSG` in `constants.py`, `ResearchContext.origin` in `context.py`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_research_node.py tests/research/test_runner.py -q`
- **Done:** suites pass

### Task 1.2 — Phu Quoc seed inventory (wave 1)

- **Files:** apps/api/app/data/hotels.py, apps/api/app/data/places.py, apps/api/app/data/content_translations.vi.json, apps/api/tests/data/test_phu_quoc_inventory.py
- **Action:** Add budget and mid-range Phu Quoc hotels and restaurants/cafes, following the existing row shape and id scheme, with vi translations.
- **Criteria:** SC-5
- **Interfaces:** Produces rows in `hotels.py`, `places.py`.
- **Verify:** `cd apps/api && ../../.venv/bin/python -m pytest tests/data -q`
- **Done:** suite passes

### Task 2.1 — Research tab asks for the origin (wave 2)

- **Files:** apps/web/src/components/trips/research/ResearchTab.tsx, apps/web/src/components/trips/research/ResearchTab.test.tsx, apps/web/src/lib/api/research.ts, apps/web/messages/en.json, apps/web/messages/vi.json
- **Action:** Start shows a required "Departing from" field and sends `origin`.
- **Criteria:** SC-4
- **Interfaces:** Consumes `startResearch` in `research.ts`; produces `ResearchTab.tsx`.
- **Verify:** `cd apps/web && pnpm vitest run src/components/trips/research`
- **Done:** tests pass

## 6. Status Log

- 2026-09-22 — tasks 1.1, 1.2, 2.1 complete
