# Research brief: LangSmith LLM Gateway, and whether it fits travel-pi

- **Date:** 2026-09-25
- **Depth:** Standard. The change touches an external system (a third-party gateway) but writes no code.
- **Status:** Research only. Nothing in the repo was changed.

## Source Pack

- [LangSmith LLM Gateway: runtime controls for production agents](https://www.langchain.com/blog/langsmith-llm-gateway-runtime-controls-for-production-agents)
- [LangSmith LLM Gateway product page](https://www.langchain.com/langsmith/llm-gateway)
- [How we made coding agent spend predictable](https://www.langchain.com/blog/how-we-made-coding-agent-spend-predictable)
- Local: the codebase map below. Every claim cites a `file:line` under `apps/api/`.

## 1. What the Gateway is (from the sources)

The Gateway is a governance proxy that sits between the agent and the model provider. You integrate it by **swapping `base_url`** and sending your LangSmith API key.

| Capability | Details | Plan / limits |
|---|---|---|
| Spend caps | Set per org, workspace, user or API key, over monthly, weekly, daily or hourly windows. Returns **HTTP 402** when a cap is exceeded. | Plus and Enterprise (public beta) |
| Rate limits | Set per org, workspace, user or API key | Plus and Enterprise |
| Fallback | Reroutes across models, providers and hosts on outages, rate limits or policy violations | Plus and Enterprise |
| PII and secret redaction | Redacts before the request reaches the provider and restores the values in the response | **Enterprise only**, by request |
| Observability | Gateway events are written as metadata on **LangSmith** traces | Needs LangSmith tracing |
| Providers | OpenAI, Anthropic, Bedrock, Gemini, Vertex, Fireworks, Baseten, and any OpenAI- or Anthropic-compatible endpoint | BYOK or Gateway Credits |
| Hosting | Runs in LangChain's datacenters (NAMER, EMEA, APAC). Self-hosting requires going through sales. | GA pricing not announced |

**Lessons from the "spend predictable" post.** These carry over to other projects more readily than the product itself:

1. **Hard limits need a workflow around them.** Warn in tiers before the threshold, then give people a fast, audited way to raise the limit.
2. **Pricing is a system, not a constant.** A price table needs a rigorous update path.
3. **Measure the delta.** Compare what the gateway captures with what the provider bills, to find traffic that bypasses it.
4. **Governance should be observability-first.** Every dollar should link back to a trace or run, so an anomaly can be debugged.

## 2. What travel-pi has today

| Control | Status | Evidence |
|---|---|---|
| Point at a gateway via `base_url` | ✅ Precedence is per-agent DB value, then provider profile, then `LLM_BASE_URL`. Works with no code change. | `app/clients/llm.py:46-49`, `app/core/config.py:134` |
| Per-user token and cost attribution | ✅ `agent_runs.user_id` (indexed) plus tokens and `cost_usd`, broken down `by_model` and `by_node` | `app/db/models/agent_run.py:16,32`, `app/agents/metrics.py:170-200` |
| Price table | ⚠️ Static, hand-updated. Prices were checked on 2026-09-03. | `app/core/pricing.py:18-30` |
| Rate limit | ⚠️ Counts **requests**, not tokens or dollars. Uses a DB-backed fixed window. | `app/core/rate_limit.py`. Limits: feedback 30/60s, web search 30/h, research 3/day |
| Tier quota | ⚠️ Free tier gets 20 turns/day. **Premium has no limit.** | `app/services/quota_service.py:14-45`, `config.py:161` |
| Per-user or per-run spend cap | ❌ None. Cost is recorded after the run and never enforced. | Searched `pricing`, `quota_service`, `rate_limit`, `agent_runs` |
| Retry | ✅ `LLM_RETRY` covers 408, 409, 429, 5xx and timeouts. The SDK is set to `max_retries=0`. | `app/agents/retry.py:31-61`, `llm.py:54` |
| Provider or model fallback | ❌ None | Searched `with_fallbacks` and `fallback` in `app/` |
| LLM request timeout | ❌ None. Only web search (10s) and research runs (600s) have timeouts. | `config.py:88`, `research/runner.py:301` |
| PII redaction | ⚠️ Credit-card numbers only (Luhn check). Emails and phone numbers are intentionally left alone. | `app/agents/guardrails.py:65-95` |
| Tracing | Uses **Langfuse**, not LangSmith. `langsmith` is only a transitive dependency of `deepagents`. | `app/agents/observability.py:39`, `requirements-ai.txt:23,78` |
| Loop ceiling | Chat recursion limit is 25. Research recursion limit is 150, plus a 600s timeout. | `config.py:155`, `research/agent.py:50` |

> The web-search cap of 6 per run is in PR #230, which is still open, so it is not on `main` yet.

## 3. Assessment: adopt the LangSmith Gateway?

**Recommendation: don't adopt it now.** Build the gateway's patterns in-house instead, reusing what the project already has.

Why:

1. **The Gateway's "user" dimension doesn't match travel-pi's user.** Gateway caps apply per LangSmith user, workspace or API key. The spend that actually needs a cap is per *end user* of the app, in particular premium users, who have no limit today. The sources say it supports "per-customer policies … without separate API keys" but don't explain the mechanism (a header? metadata?). **Unknown. Verify before believing it.** Meanwhile `agent_runs` already has exact per-end-user cost data.
2. **Observability stack mismatch.** Gateway events land on LangSmith traces. The project uses Langfuse. Adopting the Gateway means running two tracing systems, or migrating.
3. **Plan and maturity.** It needs Plus or Enterprise and is in public beta with no GA pricing. PII redaction, the feature the project lacks most, is Enterprise-only.
4. **Unverified compatibility.** The agent relies on `stream_usage=True` for OpenAI streaming (`llm.py:58`), OpenAI prompt caching (caching is already on at about 72%), and structured output with tool binding. The sources don't say whether the Gateway passes these through unchanged. **Unknown.**
5. **Error handling.** A spend cap returns **402**. `LLM_RETRY` doesn't retry 402, which is correct, but no layer turns a 402 into a friendly message for the user. Some work is needed either way.

When the Gateway *would* be worth it: several apps or teams share provider keys; you need org-level caps across many providers; or you move to Enterprise and need a PII proxy. Since switching is just `LLM_BASE_URL`, running a **trial on a dev environment** as an org-level backstop costs almost nothing, provided the plan allows it.

## 4. Proposed backlog (built in-house, highest value first)

| # | Item | Pattern from the sources | Lane (estimate) | Notes |
|---|---|---|---|---|
| 1 | **Per-user dollar budget per window** (e.g., daily or monthly), checked before each turn by summing `agent_runs.cost_usd`. Soft warning at 80%, hard stop at 100%. Covers premium users too. | Spend caps plus tiered alerting | normal | Extends `quota_service`. Needs an index on `(user_id, created_at)`; check whether it already exists. |
| 2 | **Per-run cost or token ceiling.** The metrics callback accumulates cost and stops the run once it passes the ceiling. Especially for research runs, which allow 150 recursions and 600s. | Guards against agent runaway | normal | Needs a clean stopping point that doesn't leave a tool call without its result. See the summarizer tool-pairing bug. |
| 3 | **LLM request timeout.** Pass `timeout=` into `_build_chat_model`. | Reliability | tiny | Timeouts are already retried by `LLM_RETRY`. |
| 4 | **Provider or model fallback** via `with_fallbacks` (e.g., gpt-5 → claude, or → the fast model) for 5xx or 429 after retries run out. | Fallback rules | normal | Must be applied **after** `bind_tools` or `with_structured_output`. Needs an eval run, since changing models changes behavior. |
| 5 | **Pricing as a system.** Fail loudly (log a warning or reject in the config dashboard) when a model in `agent_config` has no entry in `MODEL_PRICES_USD_PER_1M`, so cost is never silently null. Add a periodic step to re-check prices. | Pricing is a system | tiny | |
| 6 | **Measure the delta.** Once a month, compare total `agent_runs.cost_usd` with the provider invoice, to catch calls that bypass the metrics callback (background memory extraction, eval, research). | Delta measurement | tiny (a script) | |
| 7 | **Budget events on Langfuse traces.** Attach `budget_remaining` and `cap_hit` to trace metadata. | Observability-first governance | tiny | |
| — | Broader PII redaction (email, phone) | Data protection | — | Not recommended. It conflicts with the deliberate decision in `guardrails.py`, and booking flows need contact details. |

A practical backstop outside the code is to set usage or budget limits on each provider's own dashboard. Check exactly what each provider offers, since that isn't covered in this research.

## 5. Open questions

- How does the Gateway attribute spend "per customer without separate keys"?
- Does the Gateway preserve `stream_options.include_usage`, `prompt_cache_retention`, and the Responses API?
- For item 1: which window (daily or monthly), and what limit for each tier? This is a product decision.
