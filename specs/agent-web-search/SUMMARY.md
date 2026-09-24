# agent-web-search — Summary

Lane: high-risk
Confidence: medium
Reason: Hard gates `external-provider` (two new paid search APIs — Tavily and SerpAPI — plus their SDKs in the dependency manifest) and `audit/security` (two new secret API keys; untrusted web text flows into agent context and could reach the long-term memory store — prompt-injection / memory-poisoning surface). Direction is clear, but which provider does what and on which agents is an open design fork the user explicitly asked to research first.
Flags: external-provider, audit/security, external systems, existing behavior (agent routing / tool choice), public contracts (client-visible replies gain web sources), weak proof (non-deterministic web results; eval needs cassettes/fakes), multi-domain (tools + agents + prompts + config + eval)
Affects: apps/api/requirements-ai.txt (dependency manifest); app/core/config.py (off-by-default settings); new app/services/web_search_service.py + app/tools/web_search_tools.py; app/tools/registry.py (concierge group + settings-aware filter; `/agent/manifest` lists +3 tools); app/mcp/server.py (exclusion); prompts concierge v14 (active.yaml pointer); evalkit (forbidden_tools metric) + eval dataset. Research deep-agent wiring deferred (E004 = A).
Input-type: new spec
Route: brainstorming ✅ design.md (2026-09-23) → xia2 Deep ✅ research-brief.md (2026-09-23; PR #215 interaction = A, own wrapper) → writing-plans ✅ PLAN.md (2026-09-23, 7 tasks / 5 waves, review approved) → using-git-worktrees → subagent-driven-development → correctness/intent review → PR
Route-original: brainstorming (use-case catalogue + provider split, E001–E003) → xia2 Deep (external surface: Tavily + SerpAPI official docs, pricing, rate limits, LangChain integrations) → writing-plans ✅ PLAN.md (2026-09-23, 7 tasks / 5 waves, review approved) → using-git-worktrees → subagent-driven-development → correctness/intent review → PR
PR: https://github.com/minhtran3124/travel-pi/pull/227 (branch `feat/agent-web-search`, base `main`).
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

The concierge agent gets two last-resort live-web tools. `search_web` runs on Tavily and also covers current events and festivals. `find_places_live` runs on SerpAPI google_maps. A third tool, `find_events` on SerpAPI google_events, was removed after the real-key smoke run (E005): SerpAPI has deprecated that engine.

- They are bound only when `WEB_SEARCH_ENABLED` is on and the matching provider key is set. The default is off, which leaves the concierge tool list unchanged.
- Every call is rate-limited per user (30 an hour) and cached (1 h, 15 min for news, 512 entries).
- Results reach the model as escaped `<web_result>` blocks: at most 5 items, 500 chars per text field. The prompt treats them as data and cites each fact as `[title](url)`.
- The tools are excluded from MCP. `/agent/manifest` lists them.
- Concierge prompt v14 adds the last-resort rung and the "never for prices" rule.
- A generic `tools_forbidden` eval metric and 6 `web_search` goldens were added.
- The trip-research wiring is deferred until PR #221 merges (E004).

Full suite at ba156717: 2920 passed, 7 skipped. The later commit 7bc03be2 touched only the web-search files, whose tests were re-run.

### Rationale

Web search is a new external, paid, non-deterministic data source whose output is untrusted text entering the agent loop, so it lands in high-risk regardless of diff size. The user asked for a research pass on use cases before deciding when to apply each service, which maps directly to brainstorming + xia2 Deep before any plan.

### Alternatives considered

- Extend the proposed PixelRAG pipeline (`specs/web-content-enrichment/`, status: proposed, never built) instead of live search — covers static guides but not fresh/time-sensitive facts (events, advisories, opening hours); to be weighed in brainstorming, not silently dropped.
- Single provider only (Tavily or SerpAPI) — viable; the user named both, so the research decides whether both earn their place.

### Deviations

- Rule 1 (Task 1.1) — the off-defaults config test `monkeypatch.delenv`s `TAVILY_API_KEY`/`SERPAPI_API_KEY`, so the `None` default is observable under a Verify env that blanks them to `""`. `apps/api/tests/core/test_config_web_search.py`.
- Rule 1 (Task 5.1 review) — golden `web_search-ambiguous-en-02` changed from the brief's flight-price wording to a hotel-price question with `flow_match`: a flight question routes to the planner, where the web tools are never bound, so the golden could not fail. `apps/api/eval/datasets/web_search.json`.
- Rule 3 (Task 5.1) — removed stray tool markup after the closing `]` in `web_search.json`.
- Rule 3 (Task 4.2) — `ruff format` added one blank line at a pre-existing function boundary in `tests/prompts/test_concierge_prompt.py`.
- Filter location (Task 4.1, planned) — research-brief delta 7 put the filter in research `_resolve`; with research descoped (E004 = A) the filter lives only in `get_tools_for`.
- Environment (Task 1.1, controller) — the worktree `.venv` was a symlink to the main checkout's venv; installing this branch's requirements downgraded `langchain-openai` 1.6.2→0.3.34 and `openai` 3.16.2→2.54.0 there (PR #221's branch pins `langchain-openai>=1.6.2`). Restored the shared venv (`uv pip install -r <main>/apps/api/requirements.txt`, `openai==3.16.2`; `uv pip check` clean) and gave the worktree its own `.venv`.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| intake lane evidence | `python .claude/scripts/verify_summary.py --lane agent-web-search` | 0 | intake-stage record | |
| config + SDK pins | `cd apps/api && TAVILY_API_KEY= SERPAPI_API_KEY= DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/core/test_config_web_search.py -q` | 0 | 4 passed (at 7bc03be2) | SC-1 |
| service error mapping | `cd apps/api && TAVILY_API_KEY= SERPAPI_API_KEY= DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/services/test_web_search_service.py -q -k error` | 0 | 18 passed, 14 deselected (at 7bc03be2) | SC-2 |
| service cache | `cd apps/api && TAVILY_API_KEY= SERPAPI_API_KEY= DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/services/test_web_search_service.py -q -k cache` | 0 | 7 passed, 25 deselected (at 7bc03be2) | SC-3 |
| user_id gate + rate limit | `cd apps/api && TAVILY_API_KEY= SERPAPI_API_KEY= DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/tools/test_web_search_tools.py -q -k "user_id or rate_limit"` | 0 | 5 passed, 16 deselected (at 7bc03be2) | SC-4 |
| content escaping | `cd apps/api && TAVILY_API_KEY= SERPAPI_API_KEY= DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/tools/test_web_search_tools.py -q -k content` | 0 | 7 passed, 14 deselected (at 7bc03be2) | SC-5 |
| schema + error order | `cd apps/api && TAVILY_API_KEY= SERPAPI_API_KEY= DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/tools/test_web_search_tools.py -q -k "schema or error"` | 0 | 9 passed, 12 deselected (at 7bc03be2) | SC-6 |
| conditional binding | `cd apps/api && TAVILY_API_KEY= SERPAPI_API_KEY= DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/tools/test_web_search_binding.py -q` | 0 | 4 passed (at 7bc03be2) | SC-7 |
| MCP exclusion | `cd apps/api && TAVILY_API_KEY= SERPAPI_API_KEY= DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/mcp/test_mcp_server.py -q` | 0 | 8 passed (at 7bc03be2) | SC-8 |
| tools_forbidden metric | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/eval/test_metrics_deterministic.py -q -k forbidden` | 0 | 3 passed, 30 deselected (at 7bc03be2) | SC-9 |
| concierge v14 prompt | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/prompts/test_concierge_prompt.py -q` | 0 | 7 passed (at 7bc03be2) | SC-10 |
| web_search dataset | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/eval/test_datasets.py -q` | 0 | 26 passed (at 7bc03be2) | SC-11 |
| lint | `cd apps/api && ../../.venv/bin/ruff check app scripts` | 0 | All checks passed (at 7bc03be2) | |

### Correctness review (final gate, fc5a6869..560cf595)

Six FIND angles → 14 deduplicated locations → one independent scorer each (threshold 75).

Fixed (score ≥ 75, Rule 1):
- C5 (75) — places `hours` fell back to SerpAPI `operating_hours` (a dict) and reached the model as an escaped Python repr; SerpAPI events/places were uncapped. Now flattened to `day: hours; …`, both lists capped at 5 (`_MAX_ITEMS`, shared with Tavily `max_results`), each rendered field cut to 500 chars.
- C8 (75) — `web_search-ambiguous-en-01` / `-vi-01` forbade web tools without `flow_match`, so a misroute passed trivially. Both now declare `flow_match`; the dataset test requires it for every golden with `forbidden_tools`.
- Suite regression found by the branch-vs-main comparison (Rule 1): `tests/eval/test_memory_goldens.py` keeps its own taxonomy copy without `web_search`, so 3 tests failed; added the capability.

Fix re-review (round 2): C5 and C8 confirmed resolved. One new finding (85): `title`/`source` in the `<web_result>` tag were uncapped — `_esc` now cuts every value at 500 chars. Also fixed in the same round: `_hours_text` flattens nested list/dict hours (60), and `_map_tavily` slices to `_MAX_ITEMS` like the SerpAPI mappers (45).

Fix re-review (round 3, the configured cap): round 2 held, but it regressed one behaviour. Capping `source` at 500 chars would cut a long URL into a broken citation (NF-1, 70). Fixed: URLs get their own 2048-char bound. Also fixed: a mixed-type `address` list no longer raises `TypeError` (NF-4, 45). The Tavily fake now records call kwargs, and a test pins the exact argument set, so the removal of `include_published_date` is proven (NF-5, 90). Left advisory:
- NF-2 (85) — the 500 cap applies before escaping, so a field of `"` expands to at most 3000 prompt chars. It is still bounded, only by ~6× the nominal size.
- NF-3 (40) — `address`/`rating` arriving as a dict would render a repr. Latent: google_maps returns strings.
- NF-6 (60) — the ToolMessage artifact keeps the raw provider dict (capped at 5 items, fields uncapped) in the checkpoint. It has no consumer (`grep -rn "\.artifact" apps/api/app` returns nothing).

Round-3 re-review (7bc03be2): NF-1, NF-4 and NF-5 resolved; 53 targeted tests pass. The fix-round cap has been reached, so two new findings are recorded as advisory:
- (62) a mixed `address` list with `None` or dict elements now renders as `"… , None"` instead of raising. Suggested filter: `isinstance(a, str) and a`.
- (90, coverage) no test pins the 2048 `_URL_MAX` ceiling; only the lower bound is asserted.

Advisory (score < 75, not fixed — recorded for follow-up):
- C1 (50) — `include_published_date=True` is not a tavily-python 0.8.4 parameter. **Removed** after the intent review flagged it as an unverified provider decision.
- C2 (50) — availability checks `key.strip()` but the raw key is sent; a key with surrounding whitespace binds the tools and then 401s. Same pattern as the existing `ors_api_key`.
- C3 (50) — rate-limit hits are charged on every TRANSIENT_RETRY attempt (up to 3 per failing turn) and on cache hits (the latter by design).
- C4 (50) — `_map_places` ignores SerpAPI `place_results` (single-venue answer); unverified provider shape.
- C10 (50) — `WEB_SEARCH_USER_HOURLY_LIMIT <= 0` raises a raw `ValueError` in the tool; operator misconfiguration only. Fix: `Field(ge=1)`.
- C11 (50) — a new `serpapi.Client`/`requests.Session` per cache miss; freed by refcount, but no connection reuse.
- C12 (50) — SerpAPI 200 with a non-JSON body returns `str`; `dict(raw)` raises `ValueError` → `graceful_fallback` "internal fault" instead of "temporarily unavailable".
- C13 (50) — Tavily non-JSON 200 (`JSONDecodeError`) or non-200 2xx (`TypeError` inside the SDK) escape the except chain the same way.
- C14 (50) — `html.escape(quote=True)` on `url`/`title` shows the model `&amp;`/`&#x27;`; with the `[title](url)` citation rule a verbatim copy yields a broken link. Plan-mandated; mitigation would escape only `<`, `>`, `"`.
- C6 (25) — cache re-insert ordering / negative `max_entries`; unreachable in practice.
- C7 (25) — `web_search` joins the 0.7 threshold map; with the flag off it sits below threshold (adds a 4th below-threshold capability to `eval-full`; the regression gate treats it as new and does not fail).
- C9 (0) — `/agent/manifest` lists the three tools with the flag off; accepted in PLAN (manifest = registry tools), router line not in the diff.

### Intent Findings

Intent review (fc5a6869..b5a2dc9a, plan-blind), 6 findings:
- gap — `find_events` has no `weekend` filter while design.md's use-case table named one. Resolution: design.md corrected. The research brief (delta 1) dropped `date:weekend` because SerpAPI does not document it, so the code follows the evidence and the design table was stale.
- drift (behaviour) — an unverified provider decision: `include_published_date=True` was not a tavily-python 0.8.4 parameter (correctness C1). Resolution: removed. `published_date` still arrives for `topic=news`, and the mapper tolerates its absence. The SerpAPI `place_results` shape (C4) remains unverified until the owed smoke run.
- drift (behaviour, advisory) — web tools are bound to the concierge only, so a planner-routed turn cannot search. This was the user's decision (E002 = A: concierge, last resort; E004 = A: research wiring deferred).
- drift (equivalent, advisory) — three tools rather than one "search internet" tool. The user approved approach A (split by job) in brainstorming.
- excess (report-only) — the generic `forbidden_tools` / `tools_forbidden` eval metric and the `web_search` capability. They exist to prove the must-not-call use cases; they were in the plan the user saw, not in the original ask.
- excess (report-only) — the per-user hourly rate limit, the bounded TTL cache and five tuning settings. These are the E003 = A guards the user approved; they are not in the original ask.

### Not auto-verified

- Live provider behaviour — a manual real-key smoke run was done on 2026-09-24 (a scratch script calling the tools through the real service and render path, with the rate limiter stubbed). It is manual, not a re-runnable gate. Results:
  - `search_web` news (Paris strikes): 5 results, ~5.8 s.
  - `search_web` with `domains=["louvre.fr"]`: 5 results, including the opening hours.
  - `search_web` for Hoi An October events: results include the 23 Oct full-moon lantern night.
  - `find_places_live` with `hl=vi` (phở, Hoàn Kiếm): 5 places with Vietnamese hours.
  - `find_places_live` for a single venue (Sofitel Metropole): found after the C4 fix.
  - Cache hit on a repeat call: 3 ms.
  - `google_events`: HTTP 400 "Unsupported `google_events` search engine", which led to E005. SerpAPI is on the Free plan (250 searches a month).
- Visible in the smoke output: `&` in source URLs reaches the model as `&amp;` (C14, advisory). Whether the model copies it into citations is unmeasured.
- Concierge v14 with the flag off (default) — prompt names tools that are unbound; `make eval-check` on concierge goldens with the flag off not run (paid).
- Lane classification — reached traceability; flags assigned by judgment from the request, no diff exists yet to corroborate against `hooks/risk-corroboration.sh`.
- "No existing web-search tool" — searched `apps/api/app`, `apps/api/requirements.txt`, `specs/` for `tavily|serpapi|web_search|websearch`; only hit is a mention in `specs/web-trip-planner/research-brief.md`.

### Rollback

- Intake-only: `rm -r specs/agent-web-search` (nothing committed). After implementation: `git revert <sha>`; the feature ships behind off-by-default settings, so unsetting the API keys / flag disables it without a deploy.

### Minor review findings (forwarded to final review)

- Task 2.1 — `include_published_date=True` reaches Tavily via `**kwargs` as an unnamed body field; if the API rejects it, every live `search_web` fails. Offline fakes cannot catch this — covered only by the owed real-key smoke run.
- Task 2.1 (fixed in follow-up commit) — SerpAPI availability check now runs before the cache lookup; the no-results marker is honoured on a 4xx `HTTPError` too.
- Task 3.1 (fixed in follow-up commit) — the user_id gate and error-mapping tests now run across all three tools, not only `search_web`.
- Task 3.1 — the review returned `cannot_verify` on SC-4 (count mismatch it suspected); the controller re-ran all three selectors (3/5/5 passed, exit 0, test names listed) — the report count was right because the schema test name also contains `user_id`.
- Task 4.2 — concierge v14 names the three web tools unconditionally; with the flag off (default) they are unbound. The mitigation ("only when actually available; never claim a search") is prose-only and unmeasured. Owed: run the concierge-relevant eval goldens with the flag off before merge; fallback if a regression shows is conditional prompt text.
- Task 5.1 (fixed in follow-up commit) — the dataset guard now pairs each metric with its field; README matrix gains a `web_search` row and a stale-total note.
- Task 1.2 — `apps/api/evalkit/README.md:134` metric inventory omits `tools_forbidden` (and pre-existing `no_invented_date`, `no_injected_memory`, `memory_stored`).

### Change request 2026-09-24 (E005)

Removed `find_events`. The SerpAPI `google_events` engine is deprecated, and `engine=google` returned no `events_results` on 4 event queries. Event questions now go to `search_web` (Tavily, `topic=general`). `WEB_SEARCH_TOOLS = [search_web, find_places_live]`. The MCP exclusion drops the name, and the served count is still 28. Concierge v14 was edited in place because it is unreleased (never on `main`); it is still a pure insertion over v13. The golden `web_search-happy-vi-01` now expects `search_web`. C4 is fixed: `_map_places` falls back to a single `place_results` dict.

Review of the E005 change (d5918dfe..3b20af0b): no finding reached 75. The `place_results` fallback, the error mapping and the v14 insertion were verified clean. Fixed anyway because they are cheap model-facing text:
- F1 (60) — the `topic` field said "'news' for current events", which contradicted the new routing of events to `general`.
- F2 (55) — `time_range` is a publish-date recency filter. Its description now says to leave it unset for upcoming events.
Advisory: F3 (45) — Tavily calls carry no locale hint for Vietnamese event questions (the removed SerpAPI tool sent `hl`/`gl`).

### Harness-Delta

- backlog — `branch-isolation-guard` resolves the branch from the main checkout, so it flags Edit/Write into a sibling worktree as `unsafe-path:outside-root` even when that worktree is on its own task branch. The implementer used the audited `BRANCH_ISOLATION_REASON` override.
- backlog — the sibling-worktree recipe (symlink the main `.venv`) silently mutates another branch's environment when the branches pin different versions; a worktree needs its own venv when its requirements differ.
