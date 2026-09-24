# gh-229-research-web-search — Summary

Lane: high-risk
Confidence: medium
Reason: Untrusted web text flows into the trip-research dossier, which is persisted to the store per user and trip and shown to the traveller (an audit/security surface). The work also changes an existing agent's tool binding and skills, and its proof is an LLM behaviour. Three design forks have safe defaults, but they change the shape of the work: the citation format, the grader rule, and the per-run cost cap.
Flags: audit/security (untrusted content persisted in /research), external systems (paid Tavily/SerpAPI calls from a long-running job), existing behavior (research subagent tool lists, skills, grader), weak proof (LLM tool choice; live providers), multi-domain (tools + agent + skills + grader prompt)
Affects: app/research/tools.py (SUBAGENT_TOOLS), app/research/agent.py (_subagents binding), app/research/skills/{entry-and-season,day-plans,dossier-format}/SKILL.md, possibly prompts/trip_research_grader (new vN + active.yaml), app/research/reader.py (citation stripping), tests/research/*
Input-type: spec slice (follow-up of specs/agent-web-search, E004)
Route: brainstorming (E001–E003 below) → xia2 Deep (local-only: no new dependency or provider; Source Pack "none (local-only)") → writing-plans → subagent-driven-development in worktree ../travel-pi-gh-229-research-web-search (branch feat/gh-229-research-web-search from main 2b8949bf) → correctness/intent review → PR
Escalate: no (E001–E003 decided 2026-09-24: A on all three)
Issue: https://github.com/minhtran3124/travel-pi/issues/229

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> merge PR 227 rồi làm tiếp issue #229

Issue #229 (scope as filed):

> Give the trip-research deep agent the same last-resort live-web tools the concierge gets in #227 — `search_web` (Tavily) and `find_places_live` (SerpAPI Google Maps) — so a research dossier can use current information (entry rules, advisories, festivals in the trip window, live venue details) that seed data doesn't carry.

## What changed

Intake only. PR #227 was merged as 2b8949bf. The worktree and branch are created, and the forks are recorded.

### Rationale

The dossier is persisted, and it is read by the traveller with citations stripped. Web text therefore needs the same "data, not instructions" treatment, plus a citation form that survives the reader. That is a design fork, not a mechanical copy of the concierge wiring.

### Alternatives considered

- Bind the tools through `research_tools()`. Rejected: nothing in the app uses that function; the agent binds `SUBAGENT_TOOLS`.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| intake lane evidence | `python .claude/scripts/verify_summary.py --lane gh-229-research-web-search` | 0 | intake-stage record | |

### Not auto-verified

- Lane classification — reached traceability. The flags were assigned by judgement; no diff exists yet.

### Rollback

- Intake-only: `git worktree remove ../travel-pi-gh-229-research-web-search` and `git branch -D feat/gh-229-research-web-search`. After implementation: `git revert <sha>`. The tools stay behind `WEB_SEARCH_ENABLED`.

### Harness-Delta

- none
