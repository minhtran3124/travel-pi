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

### Correctness review (six angles over 2b8949bf..9ec51987)

Deduplicated into 7 locations. The fixes were cheap and unambiguous, so they were applied directly without the per-location independent scorer. This is a deviation from the correctness-review pipeline, recorded here; the fixes were re-reviewed afterwards.
- **A (4 angles, fixed).** The run cap ran after the per-user check, so every refused call still spent one of the traveller's hourly slots, and a retrying subagent could drain the chat quota. The run cap now runs first, and a test asserts `_enforce` is called 6 times for 7 calls.
- **B (4 angles, fixed).** The 86400 s window is aligned to the epoch, so a run crossing 00:00 UTC got 12 calls. It now uses a 10-year window; `run_id` is unique per run.
- **C (1 angle, by design).** A resume gets a fresh budget, because it has a new `run_id`. The design (§6) chose that start, revise and resume each get 6.
- **D (1 angle, fixed).** The budget `ToolException` was chained from `RateLimitError`, so `describe_tool_failure` took the AppError branch ("not found or not allowed"). It now raises `from None`; a test asserts `__cause__ is None`.
- **E+F (4 angles, fixed).** The verbatim `## Sources` block kept every line up to the next H1/H2, so an H3 or prose placed after the links leaked ids and tool names. A heading spelled differently lost the protection altogether. Replaced with a simpler rule: every markdown link `[title](url)` passes through untouched wherever it is, and everything else is stripped as usual. A citation after a link on the same line is stripped. Tests cover a heading variant, a trailing citation, and prose after the list.
- **G (1 angle, fixed).** The skills told the subagent to use web tools that are not bound when the flag is off. Both steps now say "If … is among your tools".
- **Fix re-review, round 2.** A, B, D and G were confirmed resolved; E+F only partly. Fixed:
  - (92) a link whose URL has parentheses and a UUID lost its line. The link pattern now allows one level of parentheses.
  - (95) a bare source URL with a UUID was dropped. Bare `http(s)://` URLs are now protected too.
  - (88) the 10-year window left one row per run that was never pruned. The window is now 7 days, so rows are pruned within 14 days; a ≤ 600 s run crosses a boundary about 0.1% of the time. This is an accepted trade-off.

- **Fix re-review, round 3 (the cap).** Round 2 held, but its bare-URL arm swallowed trailing punctuation: `https://h.example/x,` kept the comma, which then left a stray `,.`. That is fixed: a bare URL never ends in `.,;:!?)]`, and a test pins it. Accepted (85): a bare URL in body prose that embeds an internal id is now shown, because it is only ever inside a URL.
  Recorded as accepted (80, bounded): with the run cap checked first, a call the per-user limit refuses spends a run slot, and after 6 such calls the message says "run budget" rather than "hourly quota".

### Intent review (2026-09-24)

- **Gap, fixed.** The data-not-instructions sentence was missing from `entry-and-season` and `day-plans` (it existed only in `dossier-format`). It is now in both, and the test asserts it.
- **Record gap.** The smoke research run is recorded above as owed.
- **Drift, accepted.** The per-user check runs before the run cap, so a call the run cap refuses still uses one per-user token. The reverse order would spend one of the run's 6 on a call the per-user limit refuses. Of the two, the larger budget should absorb the cost.

### Harness-Delta

- none
