# agent-web-search — Summary

Lane: high-risk
Confidence: medium
Reason: Hard gates `external-provider` (two new paid search APIs — Tavily and SerpAPI — plus their SDKs in the dependency manifest) and `audit/security` (two new secret API keys; untrusted web text flows into agent context and could reach the long-term memory store — prompt-injection / memory-poisoning surface). Direction is clear, but which provider does what and on which agents is an open design fork the user explicitly asked to research first.
Flags: external-provider, audit/security, external systems, existing behavior (agent routing / tool choice), public contracts (client-visible replies gain web sources), weak proof (non-deterministic web results; eval needs cassettes/fakes), multi-domain (tools + agents + prompts + config + eval)
Affects: apps/api/requirements-ai.txt (dependency manifest); app/core/config.py (off-by-default settings); new app/services/web_search_service.py + app/tools/web_search_tools.py; app/tools/registry.py (concierge group + settings-aware filter; `/agent/manifest` lists +3 tools); app/mcp/server.py (exclusion); prompts concierge v14 (active.yaml pointer); evalkit (forbidden_tools metric) + eval dataset. Research deep-agent wiring deferred (E004 = A).
Input-type: new spec
Route: brainstorming ✅ design.md (2026-09-23) → xia2 Deep ✅ research-brief.md (2026-09-23; PR #215 interaction = A, own wrapper) → writing-plans ✅ PLAN.md (2026-09-23, 7 tasks / 5 waves, review approved) → using-git-worktrees → subagent-driven-development → correctness/intent review → PR
Route-original: brainstorming (use-case catalogue + provider split, E001–E003) → xia2 Deep (external surface: Tavily + SerpAPI official docs, pricing, rate limits, LangChain integrations) → writing-plans ✅ PLAN.md (2026-09-23, 7 tasks / 5 waves, review approved) → using-git-worktrees → subagent-driven-development → correctness/intent review → PR
Escalate: no (E001–E004 decided 2026-09-23: option A on all four)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> I have idea to allow agent travel chatbot can search internet under some conditions. Idea we can build with https://serpapi.com/ and tavily.com.
> Define tool search internet with 2 services above.
> Attach them to agent.
> Define use cases that agent need use them.
> Deep search use cases for 2 services before making decision when apply them.

## What changed

Intake only — no code yet. Classified the request, recorded the lane and the open design forks.

### Rationale

Web search is a new external, paid, non-deterministic data source whose output is untrusted text entering the agent loop, so it lands in high-risk regardless of diff size. The user asked for a research pass on use cases before deciding when to apply each service, which maps directly to brainstorming + xia2 Deep before any plan.

### Alternatives considered

- Extend the proposed PixelRAG pipeline (`specs/web-content-enrichment/`, status: proposed, never built) instead of live search — covers static guides but not fresh/time-sensitive facts (events, advisories, opening hours); to be weighed in brainstorming, not silently dropped.
- Single provider only (Tavily or SerpAPI) — viable; the user named both, so the research decides whether both earn their place.

### Deviations

- Rule 1 (Task 1.1) — the off-defaults config test `monkeypatch.delenv`s `TAVILY_API_KEY`/`SERPAPI_API_KEY`, so the `None` default is observable under a Verify env that blanks them to `""`. `apps/api/tests/core/test_config_web_search.py`.
- Environment (Task 1.1, controller) — the worktree `.venv` was a symlink to the main checkout's venv; installing this branch's requirements downgraded `langchain-openai` 1.6.2→0.3.34 and `openai` 3.16.2→2.54.0 there (PR #221's branch pins `langchain-openai>=1.6.2`). Restored the shared venv (`uv pip install -r <main>/apps/api/requirements.txt`, `openai==3.16.2`; `uv pip check` clean) and gave the worktree its own `.venv`.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| intake lane evidence | `python .claude/scripts/verify_summary.py --lane agent-web-search` | 0 | intake-stage record | |

### Not auto-verified

- Lane classification — reached traceability; flags assigned by judgment from the request, no diff exists yet to corroborate against `hooks/risk-corroboration.sh`.
- "No existing web-search tool" — searched `apps/api/app`, `apps/api/requirements.txt`, `specs/` for `tavily|serpapi|web_search|websearch`; only hit is a mention in `specs/web-trip-planner/research-brief.md`.

### Rollback

- Intake-only: `rm -r specs/agent-web-search` (nothing committed). After implementation: `git revert <sha>`; the feature ships behind off-by-default settings, so unsetting the API keys / flag disables it without a deploy.

### Minor review findings (forwarded to final review)

- Task 2.1 — `include_published_date=True` reaches Tavily via `**kwargs` as an unnamed body field; if the API rejects it, every live `search_web` fails. Offline fakes cannot catch this — covered only by the owed real-key smoke run.
- Task 2.1 (fixed in follow-up commit) — SerpAPI availability check now runs before the cache lookup; the no-results marker is honoured on a 4xx `HTTPError` too.
- Task 3.1 (fixed in follow-up commit) — the user_id gate and error-mapping tests now run across all three tools, not only `search_web`.
- Task 3.1 — the review returned `cannot_verify` on SC-4 (count mismatch it suspected); the controller re-ran all three selectors (3/5/5 passed, exit 0, test names listed) — the report count was right because the schema test name also contains `user_id`.
- Task 1.2 — `apps/api/evalkit/README.md:134` metric inventory omits `tools_forbidden` (and pre-existing `no_invented_date`, `no_injected_memory`, `memory_stored`).

### Harness-Delta

- backlog — the sibling-worktree recipe (symlink the main `.venv`) silently mutates another branch's environment when the branches pin different versions; a worktree needs its own venv when its requirements differ.
