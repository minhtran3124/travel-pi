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

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| intake lane evidence | `python .claude/scripts/verify_summary.py --lane agent-web-search` | 0 | intake-stage record | |

### Not auto-verified

- Lane classification — reached traceability; flags assigned by judgment from the request, no diff exists yet to corroborate against `hooks/risk-corroboration.sh`.
- "No existing web-search tool" — searched `apps/api/app`, `apps/api/requirements.txt`, `specs/` for `tavily|serpapi|web_search|websearch`; only hit is a mention in `specs/web-trip-planner/research-brief.md`.

### Rollback

- Intake-only: `rm -r specs/agent-web-search` (nothing committed). After implementation: `git revert <sha>`; the feature ships behind off-by-default settings, so unsetting the API keys / flag disables it without a deploy.

### Harness-Delta

- none
