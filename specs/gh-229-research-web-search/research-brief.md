# Research Brief — gh-229-research-web-search

- **Depth:** Deep, from the intake lane `high-risk`.
- **External surface:** none new. Same SDKs and providers as #227, no dependency change.
- **Date:** 2026-09-24. **Design:** `design.md`, approved.

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | Reuse. The #227 tools, `registry.available()`, `enforce_rate_limit` and `get_runtime()` all exist. Change only the subagent lists, one build-time filter, the reader's Sources carve-out, the skill text, grader v3 and one setting. |
| **Why lightest** | Every mechanism needed is already in the tree. The only new behaviour is the per-run bucket key and the Sources carve-out. |
| **Confidence** | 85% |
| **Next step** | `writing-plans`: 4 independent tasks in one wave. |

## Repo Snapshot

| Field | Detected |
|---|---|
| Stack | FastAPI, LangGraph `>=1.2.11`, deepagents `>=0.7.15,<0.8` (0.7.18 installed), Python 3.12 (Docker) / 3.14 (local) |
| Research agent | Built once at startup (`core/lifespan.py:127`), shared through `research/runtime.py:26` |
| Constraints | A new prompt means a new `vN.md` plus the `active.yaml` pointer. Skill body ≤ 500 lines. Tests are offline. |

## Feature Understanding and Assumptions

- **Requested:** issue #229, as the user asked. Web tools for the research subagents, as a last resort.
- **Success:** a research run can cite live web facts, with source links the traveller can see. With the flag off, nothing changes. Cost is bounded per run.
- **Confirmed decisions:** E001–E003 = A.

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `SUBAGENT_TOOLS` is resolved at import (`research/tools.py:76-117`). `_subagents()` reads it at `research/agent.py:138`. `_assert_bindable` uses `tool.args` (the model-facing schema), so injected `user_id`/`language` pass. |
| `Local` | `ResearchContext.run_id` (`research/context.py:14`) is the `agent_runs` id. Start, revise (`routers/research.py:261`) and resume (`service.py:225`) each create a new one. The thread id `research:{user}:{trip}` never changes, so it must not be the key. |
| `Local` | Tools already call `get_runtime(AgentContext)` and handle `RuntimeError` (`tools/date_tools.py:45`). Subagents inherit the parent runtime context through deepagents/langgraph `parent_runtime.merge`. |
| `Local` | `_CITATION = r"[ \t]*\(([^()\n]*)\)"` (`research/reader.py:23`) drops a match only when every part is a known tool or source word. A `[title](url)` link survives (tested). `_LABELLED_ID` cuts `place_id:<id>` inside URLs, and `_BARE_UUID` drops a line with a UUID (`reader.py:24-28, 79`). |
| `Local` | `_ToolIdsToContent` returns a result with no `kind` artifact untouched (`research/agent.py:244-263`). `_ToolErrorsToMessages` catches everything; the research graph has no retry policy. |
| `Local` | The grader pointer is `active.yaml: trip_research_grader: 2`. Tests pin `("trip_research_grader", 2)` and a criterion-5 phrase (`tests/research/test_skills_prompts.py:61,88`). No code parses the grader text; only `_rubric_status` is read (`runner.py:149-162`). |
| `Local` | `enforce_rate_limit` windows are aligned to the epoch (`repositories/rate_limit.py:37`). The hint on `RateLimitError` says to retry after the window (`core/rate_limit.py:89`), so the per-run cap must raise its own `ToolException`. |
| `Inference` | A 6-call cap costs at most 6 Tavily credits or SerpAPI searches per run turn, which fits the Free plan for low volume. |

## Recommendation

- **Primary:** reuse the existing primitives, as in `design.md` §2–§6.
- **Rejected:**
  - Binding through `research_tools()`: nothing in the app uses it.
  - Keying the cap on the thread id: it never resets.
  - Keying it on the config `run_id`: chat sets one too.
  - Changing the Maps fallback URL instead of the reader carve-out: that changes #227 chat output, and it does not cover UUID URLs.
- **What would change it:** deepagents no longer passing the parent runtime context to subagents. Test it through a subagent-bound tool call, not only a direct invoke.

## Risks, Unknowns, and Follow-Up Questions

- **LLM behaviour:** whether subagents follow the last-resort rule and the Sources placement is proven only by the grader and a keyed smoke run.
- **Reader:** the Sources carve-out must not leak ids back into the rest of the body. Scope it strictly to the section.
- **Grader v3 strictness:** a strict rule can fail runs where the model forgets `## Sources`. Revise turns exist for this.
- **Follow-up questions:** none. E001–E003 are decided.

## Source Pack

- **Local files read** (via the mapping agent):
  - `app/research/{tools,agent,context,state,runner,service,reader,runtime}.py`, `app/core/lifespan.py`, `app/routers/research.py`
  - `app/tools/{web_search_tools,registry,date_tools,trip_tools}.py`, `app/core/rate_limit.py`, `app/repositories/rate_limit.py`
  - `app/prompts/trip_research_grader/v1.md`, `app/prompts/trip_research_grader/v2.md`, `app/prompts/active.yaml`, `app/prompts/CHANGELOG.md`
  - `app/research/skills/{dossier-format,entry-and-season,day-plans}/SKILL.md`
  - `tests/research/{test_tools,test_skills_prompts,test_tool_ids,test_language,test_registry_snapshot,test_reader}.py`, `tests/eval/test_research_goldens.py`
  - deepagents 0.7.18 `subagents.py`, langgraph `pregel/main.py`
- **Upstream repositories or pages checked:** none found. No upstream pattern was needed for local wiring.
- **Official docs domains or pages checked:** none (local-only; no external surface).

## Evidence Boundary

> Confirmed from artifacts: all Local rows, including the reader behaviour (run by the mapping agent).
> Inferred: the cost figures, and runtime-context inheritance for the actual deepagents subagent tool calls (to be pinned by a test).
> Not checked: live model compliance with the new skill rules.
