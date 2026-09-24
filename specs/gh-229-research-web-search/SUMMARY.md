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

The trip-research subagents can now use the #227 web tools as a last resort. `entry_season` gets `search_web`; `days` gets `search_web` and `find_places_live`.

- The tools are filtered by `registry.available()` when the agent is built, so with the flag off every subagent's tools are unchanged.
- Web facts are cited `(search_web)` or `(find_places_live)`. Each such file lists its pages under a fixed English `## Sources` heading, placed before `## Ids`. The reader keeps that section byte for byte.
- Grader v3 adds criterion 7: web-cited facts need Sources, and no price may be cited to a web tool.
- A per-run cap allows 6 web calls per research run (`web_search_research_run_limit`), keyed on the `ResearchContext.run_id`. It sits on top of the per-user hourly limit; chat is never capped.

### Rationale

The dossier is persisted, and it is read by the traveller with citations stripped. Web text therefore needs the same "data, not instructions" treatment, plus a citation form that survives the reader. That is a design fork, not a mechanical copy of the concierge wiring.

### Alternatives considered

- Bind the tools through `research_tools()`. Rejected: nothing in the app uses that function; the agent binds `SUBAGENT_TOOLS`.

### Deviations

- none

### Task reviews

- **Task 1.1** (af36a52d): pass/approved. Minor: the report said 6 tests; the file has 5. The controller re-ran it: 25 passed.
- **Task 1.2** (b078b529): the reviewer returned `cannot_verify` because it could not run tests. The controller re-ran it: 28 passed. The reviewer's Minor (no `find_places_live` run-cap test) was fixed at 729c305b. Minor recorded: `get_runtime` is monkeypatched in every test, so runtime inheritance remains an open risk for the smoke run.
- **Task 1.3** (420281fe): pass/approved. Minor fixed at the next commit: trailing blank lines after the Sources links went back to the blank-run collapse. Minor recorded: the `\x00SOURCES{n}\x00` sentinel could collide only if model text contained a NUL byte, which is practically unreachable.
- **Task 1.4** (a58f27c1): needs_fixes (Important: `## Sources` was not pinned as an English heading). Fixed at 569b8425 together with the Ids-rule/Sources-URL conflict and the self-cancelling day-plans gate; re-reviewed pass. The rewrap is at cfd7440c.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| intake lane evidence | `python .claude/scripts/verify_summary.py --lane gh-229-research-web-search` | 0 | intake-stage record | |

### Not auto-verified

- Real-key smoke research run (issue #229 acceptance): **not run yet — owed.** It should show at least one fact cited `(search_web)` with a `## Sources` link and no web-cited price. It should also leave a `web_search_run` rate-limit row for that run's `run_id`; that row is the only proof that deepagents passes `ResearchContext` to subagent tool calls, because the offline tests monkeypatch `get_runtime`.
- Model compliance with the skill rules (last resort, Sources placement): unmeasured, and graded only by v3 at run time.
- Lane classification — reached traceability; the flags were assigned by judgement.

### Rollback

- Intake-only: `git worktree remove ../travel-pi-gh-229-research-web-search` and `git branch -D feat/gh-229-research-web-search`. After implementation: `git revert <sha>`. The tools stay behind `WEB_SEARCH_ENABLED`.

### Intent review (2026-09-24)

- **Gap, fixed.** The data-not-instructions sentence was missing from `entry-and-season` and `day-plans` (it existed only in `dossier-format`). It is now in both, and the test asserts it.
- **Record gap.** The smoke research run is recorded above as owed.
- **Drift, accepted.** The per-user check runs before the run cap, so a call the run cap refuses still uses one per-user token. The reverse order would spend one of the run's 6 on a call the per-user limit refuses. Of the two, the larger budget should absorb the cost.

### Harness-Delta

- none
