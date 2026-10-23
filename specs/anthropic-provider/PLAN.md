---
slug: anthropic-provider
status: draft
owner: Minh Tran
created: 2026-10-23
---

# First-class Anthropic (Claude) provider for the LangGraph agent

Inputs: epic #249 (research), Phase 1 #250, Phase 2 #251, sub-issues #252-#258. Paths are relative to the repo root; pytest means `../../.venv/bin/python -m pytest` run from `apps/api/`.

## 1. Motivation

The provider plumbing already exists (`init_chat_model`, the `anthropic`/`claude` profiles, per-agent `agent_config`), but nobody has run a keyed Claude turn through the graph. Provider-specific assumptions would break one: forced `tool_choice` in structured output (400), list-shaped `AIMessage.content`, rejected `temperature`, a stale catalog and price table, and OpenAI-only default model names.

Goals:
1. `LLM_PROVIDER=anthropic` runs a whole chat turn end to end.
2. Per-agent mixing of OpenAI and Claude works through the existing `agent_config` override.

## 2. Non-goals

- Per-request or per-user provider selection from the web UI.
- Bedrock/Vertex clients.
- `cache_creation` prompt-caching cost pricing.
- A judged full eval (`make eval-check`) on Claude.

## Global Constraints

- **Offline tests.** `make test` and `make lint` stay green on `FakeLLM`; no network in the test suite.
- **Surgical changes.** Minimum diff, match existing style, no speculative abstractions.
- **Provider-agnostic agent layer.** Provider branching lives in `app/clients/llm.py` and `app/core/llm_providers.py`, not in agent nodes.
- **Keyed runs are smoke-sized only.** T8 and the T11 keyed run use `ANTHROPIC_API_KEY` from `apps/api/.env` (authorised in the no-HITL workflow). 20-case smoke and the research smoke only; no judged eval. The DeepEval judge stays on OpenAI.
- **Git.** Stage and commit as separate commands; branch `feat/anthropic-provider`; never merge into `v5` or `main` from a task.
- **Env.** Run backend commands from `apps/api/`. If the worktree has no `.venv`, pass `VENV=<main checkout>/.venv` to make.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|---|---|---|
| SC-1 | Sampling, max_tokens and default models are provider-aware | `pytest tests/clients tests/core -q` | exit 0 |
| SC-2 | Structured output avoids forced tool_choice on Anthropic; no direct `.with_structured_output(` outside `app/clients/llm.py` | `pytest tests/clients tests/architecture tests/agents/test_multi_intent_routing.py tests/services/test_content_translation_service.py -q` | exit 0 |
| SC-3 | List-block content never leaks into user text or SSE tokens | `pytest tests/agents tests/api tests/streaming -q` | exit 0 |
| SC-4 | Claude models are priced and usage maps to a non-None cost | `pytest tests/streaming/test_record_agent_run.py tests/core/test_pricing.py -q` | exit 0 |
| SC-5 | Keyed Claude smoke has no 400s, readable output, costed `agent_run` rows | `LLM_PROVIDER=anthropic make eval-smoke` and `../../.venv/bin/python -m eval.research_smoke` | recorded in SUMMARY.md |
| SC-6 | `effort` is stored, validated and applied; dashboard form is provider-aware | `../../.venv/bin/alembic upgrade head && pytest tests/clients tests/services -q`; `pytest tests/api -q -k agent_config` | exit 0 |
| SC-7 | Cross-provider history replays without 400 | `pytest tests/agents -q -k cross_provider` plus a keyed 3-turn run | exit 0, run recorded |
| SC-8 | Embeddings warning, fixed `claude` profile URL, per-provider eval baseline | `pytest tests/core/test_embeddings.py -q` | exit 0 |
| SC-9 | Whole suite and lint are green | `make test` and `make lint` | exit 0 |

## 4. Tasks

Order: T1-T7 form Phase 1; T8 gates Phase 1; T9-T13 are Phase 2 and start only after Phase 1 (#250) closes.

Dependencies: #252 (T1-T3), #253 (T4) and #254 (T5-T6) are independent and can run in parallel. #255 (T7-T8) depends on #252, #253 and #254. #256-#258 (T9-T13) depend on #250. Inside #252, T3 builds on the profile fields from T1 and the catalog from T2; inside #256, T10 follows T9.

### Phase 1 - `LLM_PROVIDER=anthropic` works end to end (#250)

#### T1 - Provider-aware sampling and max_tokens (#252, normal)
- **Files:** apps/api/app/core/llm_providers.py, apps/api/app/clients/llm.py, apps/api/tests/clients/test_llm.py
- **Action:** add `supports_temperature` (False for `anthropic`, `claude`) and `default_max_tokens` (Anthropic 16000) to `ProviderProfile`. `_build_chat_model` forwards `temperature` only when supported (debug log once when dropped) and fills `max_tokens` from the profile unless set in `extra`.
- **Verify:** `pytest tests/clients tests/core/test_llm_providers.py -q`
- **Done:** anthropic drops temperature, openai keeps it, default max_tokens 16000, explicit DB value wins.
- **Criteria:** SC-1

#### T2 - Refresh Claude catalog and prices (#252, tiny)
- **Files:** apps/api/app/core/llm_providers.py, apps/api/app/core/pricing.py, apps/api/tests/core/test_pricing.py
- **Action:** models `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5` (keep `claude-opus-4-8`, `claude-sonnet-5`). Prices per 1M (in/out/cached): opus 4.00/20.00/0.20, sonnet 2.00/10.00/0.20, haiku 0.10/0.50/0.01. Re-check against the pricing page and update the "verified" date. Fix `normalize_model` for `anthropic/` prefixes.
- **Verify:** `pytest tests/core/test_pricing.py tests/core/test_llm_providers.py -q`
- **Done:** `estimate_cost` for `claude-sonnet-5-5` is not None.
- **Criteria:** SC-1, SC-4

#### T3 - Per-provider default models (#252, normal; after T1, T2)
- **Files:** apps/api/app/core/llm_providers.py, apps/api/app/core/config.py, apps/api/app/clients/llm.py, apps/api/.env.example, apps/api/tests/core/test_config_llm.py, apps/api/tests/clients/test_get_agent_llm_db_config.py
- **Action:** `default_model` / `default_fast_model` on `ProviderProfile` (anthropic: sonnet-5-5 / haiku-5-5); `llm_model` and `fast_llm_model` become `str | None`. Resolution: DB row, then env, then the effective provider's profile default. A per-agent provider override with no model uses that provider's default. Add an Anthropic block to `.env.example`.
- **Verify:** `pytest tests/core tests/clients -q`
- **Done:** DB row `provider=anthropic, model=None` resolves to `claude-sonnet-5-5` (Haiku for `FAST_AGENTS`).
- **Criteria:** SC-1

#### T4 - Provider-aware structured output (#253, normal, blocker)
- **Files:** apps/api/app/clients/llm.py, apps/api/app/agents/supervisor.py, apps/api/app/tools/date_tools.py, apps/api/app/services/content_translation_service.py, apps/api/tests/clients/test_llm.py, apps/api/tests/architecture/
- **Action:** add `with_structured(llm, schema)`; provider from `llm._get_ls_params().get("ls_provider")`; `anthropic` uses `method="json_schema"`, others `function_calling`. Replace the three call sites. Add an architecture guard against `.with_structured_output(` outside `app/clients/llm.py`. `FakeLLM` keeps its override.
- **Verify:** `pytest tests/clients tests/architecture tests/agents/test_multi_intent_routing.py tests/services/test_content_translation_service.py -q`
- **Done:** stub anthropic model gets `json_schema`, openai gets `function_calling`; guard passes.
- **Criteria:** SC-2

#### T5 - Read assistant text through `.text` (#254, normal, blocker)
- **Files:** apps/api/app/agents/subagents/synthesis_worker.py, apps/api/app/agents/supervisor.py, apps/api/app/agents/state.py, apps/api/app/routers/agent.py, apps/api/tests/fixtures/ (new `AnthropicShapedFakeLLM`)
- **Action:** replace `str(msg.content)` / `str(msg.content or "")` with `.text`; switch the `agent.py` truthiness check to `m.text`; leave `copy.py`. Grep `\.content` across `app/agents app/research app/memory app/routers` and convert other AIMessage reads. Add a test for `guardrails.py` non-str content.
- **Verify:** `pytest tests/agents tests/api -q -k "synth or router or state"`
- **Done:** with the Anthropic-shaped fake the user sees `"Hello"`, not `[{...}]`.
- **Criteria:** SC-3

#### T6 - Stream only text deltas (#254, normal, blocker)
- **Files:** apps/api/app/streaming/mapper.py, apps/api/tests/streaming/test_synthesize_stream_chunks.py, apps/api/tests/streaming/test_mapper_anthropic_blocks.py
- **Action:** add `_chunk_text(chunk)` (`.text` for list content, string otherwise), use it at the four read sites (~136, 156, 176, 233), skip empty strings, keep dedupe/reset keyed on message id.
- **Verify:** `pytest tests/streaming -q`
- **Done:** a text chunk emits one `token("Hi")`; a thinking-only chunk emits nothing.
- **Criteria:** SC-3

#### T7 - Cost and usage for Anthropic (#255, tiny; after T1-T6)
- **Files:** apps/api/app/streaming/agent_run.py, apps/api/app/research/runner.py, apps/api/tests/streaming/test_record_agent_run.py
- **Action:** confirm `input_token_details.cache_read` lands in the cached bucket and `response_metadata["model_name"]` is the bare model id; add the Anthropic-shaped usage test.
- **Verify:** `pytest tests/streaming/test_record_agent_run.py tests/core/test_pricing.py -q`
- **Done:** Anthropic-shaped usage gives a non-None cost.
- **Criteria:** SC-4

#### T8 - Keyed smoke on Claude (#255, normal; costs money; Phase 1 gate; after T7)
- **Files:** apps/api/eval/__main__.py (or the evalkit CLI), specs/anthropic-provider/SUMMARY.md
- **Action:** add `--provider {openai,anthropic}` (sets `LLM_PROVIDER` for the agent under test; judge stays OpenAI). Run `LLM_PROVIDER=anthropic make eval-smoke` and `../../.venv/bin/python -m eval.research_smoke`. Check: no 400s, readable streamed answers, `agent_run` rows costed, multi-turn threads survive the summarizer (`_safe_split` + `RemoveMessage`; watch "tool_use without tool_result" and preserved-thinking errors). Record results and any baseline delta.
- **Verify:** the two commands above, plus `make test` and `make lint`.
- **Done:** SUMMARY.md records the keyed smoke results.
- **Criteria:** SC-5

### Phase 2 - mix OpenAI and Claude per agent (#251; starts after #250)

#### T9 - `effort` knob on `agent_config` (#256, normal, migration)
- **Files:** apps/api/app/db/models/agent_config.py, a new Alembic migration, apps/api/app/schemas/agent_config.py, apps/api/app/services/agent_config_service.py, apps/api/app/clients/llm.py
- **Action:** nullable `effort` string; values `low|medium|high|xhigh|max`, validated in the service (`DomainValidationError`). Anthropic: `output_config={"effort": ...}` (check the langchain-anthropic 1.7.x kwarg name first). OpenAI reasoning models: `reasoning_effort`. Seed defaults: supervisor/router `low`, specialists `medium`, research `high`.
- **Verify:** `../../.venv/bin/alembic upgrade head && pytest tests/clients tests/services -q`; also `make test-docker` for Postgres.
- **Done:** effort round-trips through the service and reaches the model kwargs.
- **Criteria:** SC-6

#### T10 - Provider-aware dashboard form (#256, normal; after T9)
- **Files:** apps/api/app/templates/agent_config_edit.html, apps/api/app/routers/dashboard.py (~730-830), apps/api/app/services/agent_config_service.py
- **Action:** filter the model dropdown by provider, hide/disable `temperature` when unsupported, add the `effort` select; the service rejects non-null temperature for such providers.
- **Verify:** `pytest tests/api -q -k agent_config`
- **Done:** POST with `provider=anthropic, temperature=0.5` returns a validation error.
- **Criteria:** SC-6

#### T11 - Cross-provider history in one thread (#257, normal)
- **Files:** apps/api/app/agents/nodes.py (or a pre-model hook in `get_agent_llm` consumers), apps/api/tests/agents/
- **Action:** offline filter test first; if the keyed run (supervisor on openai, planner on anthropic, 3 turns with tool calls) returns a 400, strip `thinking`/`reasoning` blocks from AIMessages whose `response_metadata["model_provider"]` differs from the target provider.
- **Verify:** `pytest tests/agents -q -k cross_provider` plus a manual keyed run.
- **Done:** the mixed 3-turn run completes with no 400.
- **Criteria:** SC-7

#### T12 - Embeddings warning (#258, tiny)
- **Files:** apps/api/app/core/embeddings.py, README
- **Action:** log a WARNING once at startup when the provider is not OpenAI-based and `openai_api_key` is unset; document it.
- **Verify:** `pytest tests/core/test_embeddings.py -q`
- **Done:** the warning is logged once in that configuration and not otherwise.
- **Criteria:** SC-8

#### T13 - `claude` profile URL and per-provider eval baseline (#258, tiny)
- **Files:** apps/api/app/core/llm_providers.py, apps/api/eval/baselines/main-anthropic.json, the `make eval-check` wiring, apps/api/eval/README.md
- **Action:** verify `base_url="https://api.claude.com/v1"` (SDK appends `/v1/messages`); drop `/v1` or remove the profile. Add `main-anthropic.json` and pick the baseline by provider in `make eval-check`.
- **Verify:** `pytest tests/core -q` and `make -n eval-check LLM_PROVIDER=anthropic` shows the anthropic baseline.
- **Done:** the profile URL is correct or removed, and eval-check selects the baseline by provider.
- **Criteria:** SC-8

## 5. Final check

`make test` and `make lint` green (SC-9); `specs/anthropic-provider/SUMMARY.md` written; epic #249 acceptance items ticked.
