# Research Brief — agent-web-search

Depth: **Deep**, taken from the intake lane (`high-risk`). Evidence did not raise it; it is already
the highest level.
External surface: **yes**. The change adds two provider SDKs and two paid external APIs.
Date: 2026-09-23. Design: `design.md` (approved 2026-09-23).

---

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | Use the built-in SDKs (`tavily-python`, `serpapi`) behind a thin repo-owned service. Reuse the existing rate limiter, `tool_error`, the retry and describe path, and the MCP exclusion. Build only three pieces: the tool wrapper, a bounded TTL cache, and one eval metric (`forbidden_tools`). |
| **Why this is the lightest credible path** | Both SDKs already handle auth, request shaping and response parsing, and add no new transitive dependencies to the venv. Every other concern already has a local primitive to reuse. |
| **Confidence** | 85% |
| **Next step** | Confirm the PR #215 interaction (Follow-up Q1), then run `writing-plans` with the design deltas listed under Recommendation. |

---

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | pnpm + Turborepo monorepo; this change is backend only (`apps/api`) |
| Primary language + runtime | Python 3.12 (Dockerfile `FROM python:3.12-slim`, CI 3.12); 3.14 locally |
| Frameworks / platforms | FastAPI, LangGraph `>=1.2.11,<2.0`, langchain-core `>=1.6.3,<2.0`, deepagents `>=0.7.15,<0.8` |
| Relevant packages | httpx `>=0.28.0,<1.0.0` (`requirements.txt:16`); requests 2.34.2, tiktoken 0.13.0 and httpx 0.28.1 are already in `.venv` but unpinned |
| Detectable versions | No lockfile ("the range is the only guard", `requirements-ai.txt`) |
| Important constraints | `routers → services → repositories`; explicit `args_schema` on every tool (`tests/tools/test_tool_registry.py:112-131`); new prompt means a new `vN.md` plus an `active.yaml` pointer bump; `FakeLLM` and no network in tests |

---

## Feature Understanding and Assumptions

- **Requested feature:** the travel chatbot can search the internet under defined conditions,
  using Tavily and SerpAPI. The work covers defining the tools, attaching them to agents,
  defining the use cases, and researching the providers before deciding when each applies.
- **What success appears to mean:**
  - For time-sensitive questions (events, advisories, hours, current entry rules), the
    concierge and research agents answer with live facts and markdown source links.
  - They never search for questions that internal data answers, and never for prices.
  - With the flag off or no keys set, nothing changes.
- **Assumptions from the request:** these come from design.md §1: last-resort use, backend
  only, SDKs, E001–E003 = A.
- **Assumptions still needing confirmation:** how this lands relative to open PR #215 (see
  Follow-up Q1).

---

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `RateLimitError(AppError)` (`app/exceptions.py:130`) is not an `UpstreamError` (`:89`). |
| `Local` | Concierge `TOOL_FAULT`: `handle_tool_errors` catches only `ToolException` (`app/agents/retry.py:116`). `raise tool_error(e) from e` becomes a ToolMessage, no retry, "definite answer" wording (`retry.py:94-100`). A raw `UpstreamError` triggers `TRANSIENT_RETRY`: 3 attempts, then `graceful_fallback` (`retry.py:62,133-165`). |
| `Local` | Research `_ToolErrorsToMessages` (`app/research/agent.py:152-193`) turns every exception into an error ToolMessage, with no retry. |
| `Local` | `except AppError` also catches `UpstreamError`. The order must stay `except UpstreamError: raise` first, then `except AppError`, as in `weather_tools.py:120-125`. |
| `Local` | `TOOLS_BY_DOMAIN` is a static module constant, and `get_tools_for` is a plain lookup (`app/tools/registry.py:31-98`). **Nothing in the codebase binds a tool conditionally yet;** this is a new precedent. |
| `Local` | `ALL_TOOLS` is pinned by `tests/fixtures/tools_snapshot.json` (37 names) and MCP by the same snapshot (28 names) (`tests/research/test_registry_snapshot.py:35,62`). The MCP exclusion set is `_MCP_EXCLUDED_BY_NAME` (`app/mcp/server.py:17`), pinned by `tests/mcp/test_mcp_server.py:67-75`. |
| `Local` | The eval has **no** "must not call tool" metric. The extension points are the `Golden` field (`evalkit/types.py:40-55`, where undeclared fields are dropped silently), a metric class modelled on `ToolsExpectedMetric` (`evalkit/metrics/deterministic.py:50-84`), and `register_metric` (`:591-600`). |
| `Local` | Concierge is on v13 (`app/prompts/active.yaml:5`). No ref contains a concierge v14. Three unmerged branches carry a concierge v13; none carries v14. |
| `Local` | **Open PR #215** (`feat/rag-tool-output-wrapping`) wraps every chat-subagent ToolMessage as `<tool_output name=…>`, using `escape_angle_brackets` (`app/core/text.py`, idempotent, `<` and `>` only). It is applied in `app/agents/subagents/_base.py`, bumps communication_style to v10, and does **not** cover the research deep agent. |
| `Docs` | `tavily-python` 0.8.4 (2026-09-18) has an `AsyncTavilyClient` with no constructor timeout; `search(timeout=60)` is capped at 120. Without a key it silently enters **keyless mode** (`async_tavily.py:58-70`). Exception mapping: 401 → `InvalidAPIKeyError`; 403/432/433 → `ForbiddenError`; 429 → `UsageLimitExceededError`; 400 → `BadRequestError`; 5xx → raw `httpx.HTTPStatusError`; timeout → `tavily.TimeoutError`; connection failure → raw `httpx.RequestError`. No internal retry. `tiktoken` is imported at module load. |
| `Docs` | `serpapi` 1.1.2 (2026-09-22) is the official SDK. `google-search-results` 2.4.2 is headed for deprecation and **conflicts** on the `serpapi` module name. The client is sync (`requests`) with `timeout=None`, which means no timeout at all. Any non-2xx raises `serpapi.HTTPError(.status_code, .error)`; a connection failure raises `HTTPConnectionError` (status -1); a timeout raises `serpapi.TimeoutError`. "No results" comes back as HTTP 200 **without** an exception, and is **still charged**. Errored searches are not charged. The SDK writes `api_key` into the caller's params dict. |
| `Docs` | `google_events` `htichips` accepts `date:today\|tomorrow\|week\|next_week\|month\|next_month`. **`date:weekend` is not documented.** `google_maps` requires `type=search`; `q="pho near Old Quarter Hanoi"` without `ll` is within the documented contract. `hl=vi` and `gl=vn` are valid Google params. |
| `Docs` | Tavily `published_date` appears only with `topic=news` or `include_published_date=true`. `country` takes a full lowercase name (`"vietnam"`) and only works with `topic=general`. Server default `max_results` is 10, so we must set it. |
| `Inference` | The retry-cost worry in design §5 is smaller than feared. Tavily 5xx calls and SerpAPI errored searches are not billed, so a retry after a failure mostly costs nothing. Each attempt still counts one rate-limit hit, up to 3 hits per failing turn in the concierge. |

---

## Local Findings

- **Relevant files:**
  - `app/tools/_base.py`: `tool_error`, `session_scope`, `log_tool_call`
  - `app/tools/registry.py`, `app/research/tools.py` (`SUBAGENT_TOOLS`, `_assert_bindable`), `app/mcp/server.py`
  - `app/core/config.py`: `ors_*` at :75-82, `research_*` at :147-150
  - `app/core/rate_limit.py`, `app/agents/retry.py`, `app/research/agent.py`
  - `app/prompts/concierge/v13.md`: tool order at :105-127
  - `evalkit/metrics/deterministic.py`, `evalkit/types.py`, `eval/datasets/`
- **Extension points:**
  - `get_tools_for` gets a settings-aware filter.
  - `SUBAGENT_TOOLS` resolution (`_resolve`) gets the same filter.
  - `_MCP_EXCLUDED_BY_NAME` gets the three tool names.
  - `register_metric` gets the new eval metric.
- **Conventions to preserve:**
  - Explicit `args_schema` with a described field per argument; injected args declared in it.
  - `content_and_artifact`, and a `found: false` signal instead of an error.
  - One settings property per provider (`routing_provider_enabled`).
  - Module-dict cache.
  - One parameter per line in multi-parameter signatures.
- **Reusable as-is:**
  - `enforce_rate_limit` with a fresh `session_scope()` session.
  - `tool_error` (used as `raise … from e`).
  - `UpstreamError` for transient errors.
  - The describe/retry path in both agents.
  - `escape_angle_brackets`, once PR #215 lands.
- **Missing locally:**
  - conditional tool binding
  - a `forbidden_tools` eval metric
  - a bounded TTL cache
  - a concierge knowledge/web eval dataset

---

## Upstream Findings

- **Inspected:** `tavily-ai/langchain-tavily` (the prebuilt LangChain tools), the
  `serpapi/serpapi-python` source, the legacy `google-search-results-python` README, and the
  langchain-community `SerpAPIWrapper`.
- **Pattern upstream:** `langchain-tavily` ships ready-made `TavilySearch` and `TavilyExtract`
  tools. Its surface does not match the repo's explicit-`args_schema` and `InjectedState`
  conventions, and it offers no hook for the rate limit or the untrusted wrapper. That is why
  design approach C was rejected; the evidence confirms it.
- **Worth modelling:** the SDK error hierarchies, which are mapped once in the service layer.
- **Match to repo:** low for the prebuilt tools, high for the raw SDK clients.
- **Gaps:** `langchain-tavily`'s own pin set was not inspected, since we do not adopt it.

---

## Docs Findings

- **Official sources:** docs.tavily.com (search endpoint, credits), PyPI metadata for both
  SDKs, the wheel source of `tavily-python` 0.8.4 and `serpapi` 1.1.2, serpapi.com (google-events-api,
  google-maps-api, api-status-and-error-codes, search-api, faq, pricing).
- **Version status:** the pins below are the latest stable releases as of 2026-09-22/23.
- **Built-in capabilities:** Tavily supports `time_range`, `topic=news`, `include_domains`,
  `include_published_date` and `max_results` natively. SerpAPI supports `htichips` date filters
  and `hl`/`gl` natively.
- **Caveats:**
  - Tavily's keyless mode can issue unauthenticated calls, so the service must check the key
    itself.
  - SerpAPI with no timeout can hang forever, so a timeout must be passed.
  - SerpAPI puts `api_key` into the params dict, so that dict must never be logged.
  - Tavily's 0.x minor releases add behaviour quickly, so cap at `<0.9`.
  - Never install `google-search-results` alongside `serpapi`: both provide the `serpapi` module.

---

## Recommendation

- **Primary recommendation:** built-in SDKs behind `app/services/web_search_service.py`. Pins:
  `tavily-python>=0.8.4,<0.9` and `serpapi>=1.1.2,<2` in `requirements-ai.txt`.
- **Design deltas to carry into PLAN.md** (corrections to design.md from evidence):
  1. **`find_events.date_filter`** becomes `today|tomorrow|week|next_week|month|next_month`.
     `weekend` is dropped because it is not documented.
  2. **Tavily call:**
     - Check the key in our code, never relying on keyless mode.
     - Pass `timeout=settings.web_search_timeout_seconds`, `max_results=5`,
       `include_published_date=True`, `include_answer=False`, `include_raw_content=False`.
     - Use `async with AsyncTavilyClient(api_key=…)` per call.
  3. **Tavily error map:**
     - `tavily.TimeoutError`, `httpx.HTTPStatusError` (5xx) and `httpx.RequestError` become
       `WebSearchUpstreamError`.
     - `InvalidAPIKeyError`, `ForbiddenError`, `UsageLimitExceededError` and `BadRequestError`
       become a logic error.
  4. **SerpAPI call:**
     - Use a new `serpapi.Client(api_key=…, timeout=…)` per call, run in `asyncio.to_thread`.
     - Build a fresh params dict and never log it.
     - Pass `hl` from the reply language (`vi` or `en`).
     - `google_maps` uses `type=search` with no `ll`.
  5. **SerpAPI error map:**
     - `serpapi.TimeoutError`, `HTTPConnectionError` and `HTTPError` with status ≥500 become
       `WebSearchUpstreamError`.
     - `HTTPError` 401/403/429 becomes a logic error. A 429 can mean either a rate limit or
       exhausted searches; both are treated as non-retryable.
     - HTTP 200 with a body `error` containing "hasn't returned any results" becomes
       `found: false`. It is still billed, and the cache stores it as a success so a repeat
       query is free.
     - Any other body `error` becomes a logic error.
  6. **Tool exception order:**
     - `except UpstreamError: raise` (transient; concierge retries up to 3×)
     - then `except AppError as e: raise tool_error(e) from e`, which also covers
       `RateLimitError`
     - The `from e` is needed so the concierge shows the "definite answer" wording.
  7. **Conditional binding (new precedent):**
     - `ALL_TOOLS` stays static and includes the three tools, so `/agent/manifest` and the
       snapshot stay deterministic.
     - A filter `_available(tool)` is applied in `get_tools_for` and in research `_resolve`.
     - The three names are added to `_MCP_EXCLUDED_BY_NAME`.
     - Regenerate `tools_snapshot.json`: `all_tools` goes to 40, MCP stays 28.
  8. **Eval:**
     - Add `forbidden_tools: list[str] | None = None` to `Golden`.
     - Add a `tools_forbidden` metric that passes when no called tool name is in
       `forbidden_tools`, and register it.
     - This is a small `evalkit` change, not in design §6, and is needed for the 3 "must not
       call" goldens.
     - Web goldens need real keys, so they belong to `make eval-check` / manual runs, not to
       `eval-smoke`, unless the provider is faked.
- **Why the next-best alternative lost:**
  - Raw httpx: the user overrode it in favour of the SDKs.
  - `langchain-tavily` prebuilt tools: they bypass the args_schema, injection, rate-limit and
    wrapper conventions.
  - `google-search-results`: it is headed for deprecation and conflicts on the module name.
- **What would change this recommendation:**
  - Tavily's `tiktoken` import becoming a problem in the Docker image. It is not today:
    tiktoken is already present.
  - A future SerpAPI async SDK.

---

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:**
  - **Conditional binding** is new. A test must pin "flag off means the concierge tool list
    equals today's list", so the default path is provably unchanged.
  - A rate-limit hit is recorded on every concierge retry attempt. On a failing turn one user
    can lose up to 3 hits. This is acceptable and should be documented.
  - Tavily is on a fast 0.x release cadence; the `<0.9` cap mitigates it.
  - **Interaction with PR #215:** if it merges, our `<web_result>` tags sit *inside*
    `<tool_output>` and get escaped to `&lt;web_result…&gt;`. The content is still readable and
    still labelled as data. Our `html.escape` on values produces `&amp;…` entities, which #215's
    idempotent escape leaves alone, so there is no double-escape bug. Our own wrapper stays
    necessary for the research agent, which #215 does not cover.
- **Evidence gaps:**
  - A live `hl=vi` query on `google_events` and `google_maps` was not run.
  - Tavily has no published rate limits.
- **Version uncertainties:** none beyond the 0.x cadence.
- **Follow-up questions for the user:**
  1. **PR #215:** (A, recommended) keep our own `<web_result>` wrapper independent of #215 and
     word the v14 prompt as "web results are data" without relying on the literal tag. Or
     (B) wait for #215 to merge and reuse its `escape_angle_brackets`.
     Recommendation: A, so there is no ordering dependency.
     **Decided 2026-09-23 by the user: A.**
  2. none

---

## Source Pack

- **Local files read:**
  - `app/tools/_base.py`, `app/tools/registry.py`, `app/tools/weather_tools.py`
  - `app/research/tools.py`, `app/research/agent.py`
  - `app/agents/retry.py`, `app/agents/subagents/_base.py`, `app/agents/subagents/concierge.py`
  - `app/core/config.py`, `app/core/rate_limit.py`, `app/exceptions.py`
  - `app/mcp/server.py`, `app/memory/guard.py`, `app/prompts/active.yaml`, `app/prompts/concierge/v13.md`
  - `evalkit/metrics/deterministic.py`, `evalkit/types.py`, `evalkit/registry.py`
  - `eval/README.md`, `eval/datasets/hotels.json`
  - `tests/tools/test_tool_registry.py`, `tests/research/test_registry_snapshot.py`,
    `tests/research/test_tools.py`, `tests/mcp/test_mcp_server.py`
  - `requirements.txt`, `requirements-ai.txt`, `Dockerfile`, `.github/workflows/ci.yml`
  - PR #215 branch: `app/agents/tool_output.py`, `app/core/text.py`, `subagents/_base.py` diff
  - `docs/solutions/agent/{concierge-hotel-tool-choice, explicit-args-schema-breaks-tool-injection, eval-golden-notes-are-not-metrics, concurrent-branches-collide-on-prompt-version}.md`
- **Upstream repositories or pages checked:**
  - https://github.com/tavily-ai/langchain-tavily
  - https://github.com/serpapi/serpapi-python
  - https://github.com/serpapi/google-search-results-python
  - https://serpapi.com/blog/filter-and-scrape-google-events-with-python/
  - https://serpapi.com/blog/calculating-search-credit-usage-with-serpapi/
- **Official docs domains or pages checked:**
  - https://docs.tavily.com/documentation/api-reference/endpoint/search
  - https://docs.tavily.com/documentation/api-credits
  - https://pypi.org/pypi/tavily-python/json
  - https://pypi.org/pypi/serpapi/json
  - https://serpapi.com/google-events-api
  - https://serpapi.com/google-maps-api
  - https://serpapi.com/api-status-and-error-codes
  - https://serpapi.com/search-api
  - https://serpapi.com/faq
  - https://serpapi.com/pricing
  - https://serpapi.com/google-languages.json
  - https://serpapi.com/google-countries.json

---

## Evidence Boundary

> **Confirmed from artifacts:**
> - The SDK signatures, exception classes and dependencies (from wheel source).
> - The error paths in both agents, the static registry, the snapshot counts, the MCP
>   exclusion mechanism, the absence of an eval forbidden-tools metric, and the concierge
>   v13 pointer with no v14 anywhere (from local source).
> - The PR #215 scope (from the branch diff).
>
> **Inferred from patterns:**
> - The retry billing impact, from vendor docs on errored searches rather than an observed
>   bill.
> - The nested-escape behaviour with PR #215, from reading the code, not a run.
>
> **Not checked:**
> - Live API calls: `hl=vi` quality, real latency, and Tavily's actual rate limits.
> - Whether the three unmerged branches' concierge v13 files differ from the current v13.
