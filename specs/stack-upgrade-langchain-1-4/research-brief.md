---
slug: stack-upgrade-langchain-1-4
doc: research-brief
created: 2026-09-18
depth: Deep
---

# Research brief — stack-upgrade-langchain-1-4

Depth: **Deep** (high-risk lane: dependency manifest = external surface). Coverage: local import
inventory (`grep` over `apps/api/app`, `tests`, `eval`, `evalkit`), PyPI metadata for every moved
package, upstream release notes, and the target wheels unpacked and grepped for every symbol the app
imports.

## Source Pack

- PyPI JSON: `deepagents/0.7.15`, `langchain/1.4.1`, `langchain-core/1.6.3`, `langchain-anthropic/1.7.2`, `langchain-openai` (latest 1.6.2)
- deepagents 0.7.15 wheel METADATA (floors that motivate this change)
- GitHub release notes: langchain-ai/langchain (core 1.4.9…1.6.3, langchain 1.3.12…1.4.1, anthropic 1.4.8…1.7.2, openai 0.3.35 / 1.0.0…1.6.2), langchain-ai/langgraph (1.2.7…1.2.11, checkpoint 4.2.0, checkpoint-postgres 3.1.1/3.1.2, checkpoint-sqlite 3.1.1), langchain-ai/langchain-google (genai 4.2.2…4.4.0), langchain-ai/langsmith-sdk (0.9.3…0.12.6)
- Local: `apps/api/requirements.txt`, `requirements-ai.txt`, `.venv` pip metadata, `app/agents/retry.py`, `app/agents/subagents/_base.py`, `app/memory/store.py`, `app/clients/llm.py`

## Resolution outcome (fresh Python 3.12 venv = Docker interpreter)

| package | before (prod `.venv`) | after | note |
|---|---|---|---|
| langchain | 1.3.11 | 1.4.1 | requires langgraph>=1.2.11 |
| langchain-core | 1.4.8 | 1.6.3 | explicit floor added |
| langgraph | 1.2.6 | 1.2.11 | |
| langgraph-prebuilt | 1.1.0 | 1.1.0 | no newer release exists |
| langgraph-checkpoint | 4.1.1 | 4.2.0 | |
| langgraph-checkpoint-postgres / -sqlite | 3.1.0 / 3.1.0 | 3.1.2 / 3.1.1 | namespace-prefix boundary fix (#8478) |
| langchain-anthropic | 1.4.7 | 1.7.2 | |
| langchain-google-genai | not installed | 4.4.0 | default temperature removed for Gemini (4.3.0) |
| langchain-openai | 0.3.34 | **0.3.34** | cap `<1.0` untouched — see decision below |
| openai SDK | 2.44.0 | 2.54.0 (3.12 venv) / 2.44.0 (root venv) | |
| langsmith | 0.9.2 | 0.12.6 (3.12 venv) / 0.9.2 (root venv) | transitive; no direct import in app |
| deepeval / agentevals / openevals | unchanged | unchanged | none pin langchain-core |

`uv pip check`: clean on both venvs. fastapi/starlette/pydantic caps untouched.

## Decision: langchain-openai stays on 0.3.x in this PR

The resolver keeps `langchain-openai 0.3.34` because of the repo's `<1.0` cap. 0.3.34 is the last
0.3.x whose metadata admits core 1.x (0.3.35 pins `langchain-core<1.0`), and production has already
been running 0.3.34 against core 1.4.8. Moving to 1.6.2 is a separate major jump (stream-chunk
timeout raising `StreamChunkTimeoutError` after 120 s silence since 1.2.0, `cache_creation` usage
keys and `prompt_cache_retention` since 1.3.5, `ModelError` hierarchy since 1.6.0, `openai>=2.45`)
that touches the production provider path and the prompt-caching work — out of scope here and
recorded as follow-up. The behavioural gate for the 0.3.34 + core 1.6.3 combination is `eval-smoke`
against the real provider (SC-5).

## Risk list → what was checked

| # | Risk (source) | Check | Result |
|---|---|---|---|
| 1 | core 1.6.0 #39602: injected-arg detection now resolves postponed annotations; all tools declare `args_schema` (PR #204) | full suite incl. `tests/agents/`, `tests/tools/` on both interpreters | 2806 passed SQLite (3.12), 2808 passed Postgres (Docker) |
| 2 | core 1.5.5 #39535: `AIMessageChunk` merge raises on bool conflicts | `tests/api/agent/test_stream_events.py` (16 hand-built chunks) in the suite | passed |
| 3 | core 1.6.0 #39306/#39570: strict / forward-ref tool schemas | `grep -rnE "strict=True\|ForwardRef\|model_rebuild" app/tools app/agents` | 2 hits, both `zip(..., strict=True)` — not schema |
| 4 | langgraph 1.2.7–1.2.9 DeltaChannel/Overwrite fixes | `grep -rnE "DeltaChannel\|Overwrite\(" app` | 0 |
| 5 | checkpoint-postgres 3.1.1 #8478 namespace-prefix boundary | `app/memory/store.py::_namespace` = `("users", user_id, kind)`, always searched with the full 3-tuple | no prefix search on a partial namespace; fix is neutral-to-positive |
| 6 | langgraph-prebuilt private API (`ToolInvocationError.filtered_errors`, `_infer_handled_types`) | prebuilt unchanged at 1.1.0 | n/a |
| 7 | removed 1.0 APIs (`callback_manager`, `.predict(`, `call_as_llm`) | grep over app/eval/evalkit | 0 |
| 8 | langsmith 0.12 httpx2 | `uv pip check` | clean |
| 9 | new deprecation warnings | warnings-summary diff old vs new (same cwd, no `.env`) | no new `langchain*`/`langgraph*` warning; remaining diff = py3.12 vs py3.14 line numbers and a starlette httpx2 notice present only on the baseline interpreter |

## eval-smoke comparison

Baseline (old stack, root `.venv`, real provider): 16/18 — `dates-ambiguous-en-02` (invented date) and
`journal-happy-en-01` (routed to planner) fail; both are pre-existing prompt/routing misses.

New stack: see SUMMARY `### Verify` SC-5 row.

## Appendix — full upstream changelog scan

## 1. `langgraph.prebuilt` — ToolNode, tools_condition, InjectedState/InjectedStore, ToolInvocationError, `_infer_handled_types`

**None found.** `langgraph-prebuilt` has had no release since 1.1.0 (2026-05-12); langgraph 1.2.11 still pins `>=1.1.0,<1.2`.
The installed `langgraph/prebuilt/tool_node.py` (1.1.0) is what will run after the upgrade: `class ToolInvocationError(ToolException)`
at line 339 with `self.filtered_errors` at 379, `_infer_handled_types` at 444. `app/agents/retry.py:72-73` and
`app/agents/subagents/_base.py:266,271` keep working unchanged.

Source: https://github.com/langchain-ai/langgraph/releases (no `prebuilt==` tag after 1.1.0); https://pypi.org/pypi/langgraph-prebuilt/json.

One indirect effect (core, not prebuilt): `_infer_handled_types` reads the handler's parameter annotation; nothing in core 1.6 changes
that path. But core #39602 changes how `StructuredTool` detects injected args (see §4c), which is what decides whether a missing
`InjectedState` key surfaces as `ToolInvocationError` with empty `filtered_errors` (your "missing runtime context" branch) — retest #113/#125 cases.

## 2. `langgraph` core — NodeError, RetryPolicy, Command, Send, interrupt, Runtime/get_runtime, context_schema, MessagesState, add_messages

All symbols present in the 1.2.11 wheel (`errors.py`, `types.py`, `runtime.py`, `graph/message.py`). Release notes 1.2.7–1.2.11 contain no changes to them.

| version | change | source |
|---|---|---|
| 1.2.7 | fix: snapshot `DeltaChannel` overwrite supersteps (#8125); `Overwrite` survives JSON roundtrips (#8127); valid UUIDs for exit-mode delta task_ids (#8165) | https://github.com/langchain-ai/langgraph/releases/tag/1.2.7 |
| 1.2.8 | fix: `update_state` on a fresh thread with delta channel forces snapshot instead of stub checkpoint (#8290) | https://github.com/langchain-ai/langgraph/releases/tag/1.2.8 |
| 1.2.9 | fix: `update_state` metadata/counters for delta channel (#8315) | https://github.com/langchain-ai/langgraph/releases/tag/1.2.9 |
| 1.2.10 | feat: `trace_policy` on `add_node` (#8362); `TracePolicy` tags dropped then TracePolicy class deleted/reverted (#8402/#8403); typed v3 `stream_events` return (#8389) | https://github.com/langchain-ai/langgraph/releases/tag/1.2.10 |
| 1.2.11 | `trace_policy` on `add_node` re-landed (#8523); bundles checkpoint 4.2.0 + checkpoint-postgres 3.1.2 | https://github.com/langchain-ai/langgraph/releases/tag/1.2.11 |

Behavioral: none for your graph unless you use `DeltaChannel`/`Overwrite` (grep: `rg "DeltaChannel|Overwrite\(" apps/api/app` → not checked; do it).

## 3. Checkpointers and stores

| package | version | change | source |
|---|---|---|---|
| langgraph-checkpoint | 4.1.1 → 4.2.0 | `TTLConfig.omit_expired: bool` (default False, opt-in): Postgres store reads (`get`/`search`/`list_namespaces`) filter `expires_at` at query time instead of waiting for the sweeper (#8354). Fix: `InMemorySaver.get_delta_channel_history` dropped the first write after migrating a thread to DeltaChannel (#8526). `BaseStore.search(namespace_prefix, /, *, query=None, filter=None, limit=10, offset=0)` signature unchanged (verified in wheel). No InMemoryStore TTL/index changes in notes (the known "InMemoryStore raises on TTL" behavior from memory is untouched). | https://github.com/langchain-ai/langgraph/releases/tag/checkpoint%3D%3D4.2.0 |
| langgraph-checkpoint-postgres | 3.1.0 → 3.1.1 | **Behavior change**: store namespace scoping matched `LIKE '<path>%'` — a search scoped to `("foo",)` also returned `("foobar",)` rows. Now exact-or-separator-bounded; pattern metachars in labels escaped; `*` in `list_namespaces` spans exactly one segment (#8478). `omit_expired` support (#8354). | https://github.com/langchain-ai/langgraph/releases/tag/checkpointpostgres%3D%3D3.1.1 |
| langgraph-checkpoint-postgres | 3.1.1 → 3.1.2 | fix: find plain-value seeds when walking delta history (#8535); conformance suite now run (#8537) | https://github.com/langchain-ai/langgraph/releases/tag/checkpointpostgres%3D%3D3.1.2 |
| langgraph-checkpoint-sqlite | 3.1.0 → 3.1.1 | same namespace-boundary fix (#8478) | https://github.com/langchain-ai/langgraph/releases/tag/checkpointsqlite%3D%3D3.1.1 |
| AsyncPostgresSaver / PostgresStore / InMemoryStore API | | no signature changes found in these notes | same |

App surface: `app/memory/store.py` uses `PostgresStore.from_conn_string(..., index=_index_config())`, `InMemoryStore(index=...)`,
`store.search(ns, limit=_PAGE_SIZE, offset=offset)` and `store.search(ns, query=..., limit=...)` — all still valid.

## 4. langchain-core 1.4.8 → 1.6.3 and langchain 1.3.11 → 1.4.1

### 4a. `init_chat_model` (langchain)
Signature unchanged in the 1.4.1 wheel: `init_chat_model(model, *, model_provider=None, configurable_fields=None, config_prefix=None, **kwargs)`.
Additions only: LangSmith provider (1.3.15, #39224), `meta` extra (1.3.13), `langchain.mcp`/`MCPAdapter` namespace (1.4.0, #39939).
Everything else in 1.3.12–1.4.1 is `create_agent` middleware (HITL, ToolRetry, Summarization, PII, ContextEditing, ToolCallLimit) — not used by this graph.
Sources: https://github.com/langchain-ai/langchain/releases/tag/langchain%3D%3D1.4.0 , …/langchain%3D%3D1.4.1 , …/langchain%3D%3D1.3.15 , …/langchain%3D%3D1.3.13 .

### 4b. Symbol survival in core 1.6.3 (grepped in wheel)
`messages.ai.add_usage` ✔, `embeddings.fake.DeterministicFakeEmbedding` ✔, `vectorstores.in_memory.InMemoryVectorStore` ✔,
`tools.base.ToolException` ✔, `tools.InjectedToolCallId` ✔, `callbacks.base.BaseCallbackHandler` ✔,
`language_models.chat_models.BaseChatModel.with_structured_output` ✔, `outputs.ChatResult/ChatGeneration` ✔ (imported by your `FakeLLM`).
`.text()` callable still exists but has been deprecated since 1.0 (use `.text` property) — `rg "\.text\(\)" apps/api/app apps/api/tests` → 0 hits.

### 4c. Changes that can alter behavior (core)
| version | change | why it matters here | source |
|---|---|---|---|
| 1.6.0 | `StructuredTool._injected_args_keys` resolves postponed annotations with `typing.get_type_hints(include_extras=True)`; per-annotation fallback if one forward ref fails (#39602) | 10 of `app/tools/*.py` use `from __future__ import annotations` and every tool declares `args_schema` (PR #204). Before: injected params could be missed → stripped at validation → `ToolInvocationError`; after: detected and hidden from the model schema. Tool-schema snapshots and the #113 "missing injected arg" classification path can change. | https://github.com/langchain-ai/langchain/releases/tag/langchain-core%3D%3D1.6.0 , PR #39602 |
| 1.5.4 | injected args honoured for `BaseTool` subclasses (#39202); `include_injected=False` respected with `filter_args` (#39200); flat args schema preserved for `RootModel` runnables (#39307); reserved tool argument names documented (#39207) | same area as above | https://github.com/langchain-ai/langchain/releases/tag/langchain-core%3D%3D1.5.4 |
| 1.5.5 | tool input validation keeps fields supplied via pydantic aliases (#39572); tool descriptions handled for `infer_schema=False` (#39573); `tool_example_to_messages` raises on tool_outputs/tool_calls length mismatch (#39142) | any `Field(alias=…)` in tool args schemas now works differently | https://github.com/langchain-ai/langchain/releases/tag/langchain-core%3D%3D1.5.5 |
| 1.5.5 | **`merge_dicts` raises `TypeError` for differing bools at the same key** (was `True+False → 1`); **`AddableDict.__add__` raises on incompatible types instead of silently dropping**; `merge_lists` no longer treats non-dict items as index-keyed (#39535) | affects `AIMessageChunk + AIMessageChunk` in streaming: `additional_kwargs`/`response_metadata` bools that differ across chunks now blow up instead of merging. Fakes that hand-build chunks are the likely tripwire. | PR #39535 release note |
| 1.5.5 | usage-metadata callback context manager cleared on exceptions (#39616); falsy caches handled (#39283); malformed Anthropic content blocks guarded (#38670) | `metrics.py` uses its own `BaseCallbackHandler`, not `get_usage_metadata_callback` — low impact | same |
| 1.6.0 | **standard model exception types** `langchain_core.exceptions.ModelError` (+ auth / invalid-request / rate-limit / timeout …) with `.is_retryable`; providers raise classes inheriting from BOTH SDK type and LangChain type (#39538) | `isinstance` on SDK exceptions keeps working; `retry.py:_is_retryable_llm` (status-code + class-name list) could be replaced by `is_retryable`. Only providers ≥ core 1.6 raise them (anthropic 1.6.0, openai 1.6.0, genai 4.3.5) — **langchain-openai 0.3.34 does not**. | https://github.com/langchain-ai/langchain/releases/tag/langchain-core%3D%3D1.6.0 |
| 1.6.0 | `convert_to_openai_function(strict=True)` recursively puts all nested props in `required` (#39306); fail-fast when tool schemas can't resolve forward refs during serialization (#39570); `convert_to_openai_function` accepts callables/non-dict mappings (#39750); `StructuredTool` JSON-serializable (1.6.1, #39631) | affects strict tool/structured-output schemas sent to OpenAI; forward-ref'd pydantic models in tool args now error at bind time rather than silently producing empty schemas | same |
| 1.5.0 | `reasoning_effort` added as a standard chat-model parameter (#38887) — lives in `model_profile.py`; no `BaseChatModel` signature change | harmless | https://github.com/langchain-ai/langchain/releases/tag/langchain-core%3D%3D1.5.0 |
| 1.5.1–1.5.3, 1.5.6, 1.6.1, 1.6.3 | LangSmith **gateway** support via env vars (#38742), `LANGSMITH_API_KEY` fallback (#39115), empty-string env handling (#39107), gateway metadata into traces / on error path / model-name override from gateway response (#39703, #39829, #40406) | only active if gateway env vars are set | respective release tags |
| 1.4.9 | output parser fixes in `xml.py`/`pydantic.py` (#35641); `asyncio.get_running_loop()` in async contexts (#38157); `dict` shadowing fix (#38480) | `with_structured_output(method="function_calling")` uses `PydanticToolsParser` — regression-test `supervisor.py:316`, `date_tools.py:64` | https://github.com/langchain-ai/langchain/releases/tag/langchain-core%3D%3D1.4.9 |
| 1.5.5 | `httpx` becomes an explicit core dependency (#39612) | none | … |

### 4d. `BaseChatModel` subclassing for fakes (`_generate` / `ChatResult`)
None found in core 1.4.9–1.6.3 notes. `app/clients/llm.py:FakeLLM` (`_llm_type`, `_generate` → `ChatResult(generations=[ChatGeneration(...)])`,
`bind_tools`, `with_structured_output`) and the two test-only subclasses keep the same contract. Only #39535 (chunk merging) can bite if a fake streams chunks.

### 4e. Callbacks (`BaseCallbackHandler`)
None found. `TurnMetricsHandler` reads `usage_metadata["input_token_details"]["cache_read"]` and calls `add_usage` — both unchanged.

## 5. langsmith-required / tracing defaults / uuid-utils / langchain-protocol
- `langsmith`, `uuid-utils`, `langchain-protocol` are **already hard requirements of the installed core 1.4.8** (`pip show langchain-core` → Requires: … langchain-protocol, langsmith, … uuid-utils). Nothing new becomes required in 1.6.3 except `httpx`.
- No change to tracing defaults (`LANGSMITH_TRACING` / `LANGCHAIN_TRACING_V2`) found in core 1.4.9–1.6.3 release notes.
- langsmith 0.9.2 → 0.12.6: 0.12.0 items flagged `!` — deterministic trace sampling (#3183), **httpx2 dependency with httpx fallback** (#3406), anonymizer callables fail-closed (#3328); 0.10.x removed `AsyncClient.projects` (#3163), composite feedback-formula APIs (#3248), `get_run_stats` requires project (#3250); 0.11.0 stops re-sending run inputs on patch by default (#3396). App has **no direct langsmith import** (`rg "^from langsmith|^import langsmith" apps/api/app apps/api/eval apps/api/tests` → 0), so only the transitive httpx2 install matters.
  Sources: https://github.com/langchain-ai/langsmith-sdk/releases/tag/v0.12.0 , …/v0.11.0 , …/v0.10.0 .

## 6. langchain-openai — two separate cases

### 6a. Staying on langchain-openai 0.3.34 while core moves 1.4.8 → 1.6.3 (the resolver's actual outcome)
0.3.34 imports from core only: `BaseTool, ChatGeneration, ChatGenerationChunk, ChatResult, deprecated, from_env, get_pydantic_field_names,
JsonOutputParser, PydanticOutputParser, run_in_executor, secret_from_env, tool_call_chunk, LanguageModelInput, _build_model_kwargs, _stringify`
(grepped `.venv/…/langchain_openai/chat_models/base.py`). All still exist in 1.6.3. What actually changes under it:
1. **Streaming chunk merge** (core 1.5.5 #39535): `ChatGenerationChunk`/`AIMessageChunk` addition now raises `TypeError` on bool conflicts or incompatible types where 1.4.8 silently summed/dropped. 0.3.34 puts `service_tier`, `system_fingerprint`, `model_name` etc. into `response_metadata` of chunks — strings, so normally fine; but any bool it emits that flips between chunks (none known) would now raise.
2. **Tool schema conversion** (core 1.6.0 #39306/#39570/#39750): 0.3.34 calls core's `convert_to_openai_tool`; strict schemas now require all nested properties; unresolvable forward refs fail fast.
3. **Injected-arg detection** (core 1.6.0 #39602) — tool side, provider-agnostic (see §4c).
4. **Exceptions**: 0.3.34 keeps raising raw `openai.*` SDK errors; `ModelError` hierarchy is NOT produced. `_is_retryable_llm` unchanged in effect.
5. **Usage metadata**: 0.3.34 already emits `input_token_details.cache_read` (2 hits in file) — no `cache_creation`, no service-tier prefixes. Unchanged.
6. **Not available on 0.3.34**: `prompt_cache_retention` (0 hits), `stream_chunk_timeout` (0), `OPENAI_BASE_URL`-aware `stream_usage` default (0). `reasoning_effort`/`reasoning`, `use_responses_api`, `output_version`, `prompt_cache_key`, `service_tier`, `verbosity`, `OpenAIRefusalError` ARE present in 0.3.34.
7. Risk of the combination itself: 0.3.35 (one patch later) pinned `langchain-core<1.0`; 0.3.34 only escapes that by accident. No upstream CI ever ran 0.3.x against core 1.5/1.6. Standard-tests contract changes (v1 content blocks, `output_version`) are invisible to 0.3.34.
Conclusion: workable but unsupported; test coverage is the only guard.

### 6b. Moving to langchain-openai 1.6.2 (requires lifting the `<1.0` cap and `openai>=2.45`)
| version | behavior change | source |
|---|---|---|
| 1.0.0 | Python ≥3.10; deprecated items removed (#33192: `callback_manager`, `predict*`, `__call__`, `call_as_llm`, `PipelinePromptTemplate`, `tracing_enabled`, `InMemoryVectorStore.upsert`, …); `stream_usage` **defaults to True only when using the default base URL/client** and is left off if `OPENAI_BASE_URL`/`base_url` is set (#33205/#33298) — your `_build_chat_model` passes `stream_usage=True` explicitly, which wins (verified 1.6.2 `base.py:1362-1375`); `invoke` with `streaming=True` delegates to core (#33308); service-tier token details populated (#32721) | https://github.com/langchain-ai/langchain/releases/tag/langchain-openai%3D%3D1.0.0 |
| 1.1.1–1.1.3 | Responses API + built-in tools fixes; `tools` param added to `with_structured_output` (#34075); `temperature` allowed when `reasoning="none"` (#34298); `strict` flag for ProviderStrategy (#34149); gpt-5.2-pro → Responses API | …/langchain-openai%3D%3D1.1.2 |
| 1.1.7 | structured-output refusal raises `OpenAIRefusalError` (#34619) — already in 0.3.34 | …/langchain-openai%3D%3D1.1.7 |
| 1.1.11–1.1.13 | Responses API model detection for pro/codex; pydantic serialization warning fix for structured output (#35543); is-not-None checks in usage-metadata extraction (#36500) | … |
| 1.1.16 | tolerate `prompt_cache_retention: "in_memory"` vs SDK literal `"in-memory"` drift in streaming (#36925) | …/langchain-openai%3D%3D1.1.16 |
| **1.2.0** | **streams raise `StreamChunkTimeoutError` (subclass of `TimeoutError`, NOT `httpx.TimeoutException`) after 120 s of parsed-chunk silence** (#36949). Opt-out: `stream_chunk_timeout=None` or `LANGCHAIN_OPENAI_STREAM_CHUNK_TIMEOUT_S=0`. Also custom httpx transport with TCP keepalive/`TCP_USER_TIMEOUT`; skipped automatically when proxy env vars are present and no custom client is supplied. | …/langchain-openai%3D%3D1.2.0 |
| 1.3.3 | drop response item ids when `store=False`; drop `stop` from Responses payload | …/langchain-openai%3D%3D1.3.3 |
| 1.3.4 | suppress pydantic serializer warning on structured-output `parsed` field (#37727) | … |
| **1.3.5** | **explicit prompt caching** (#38762): `prompt_cache_key` / `prompt_cache_retention` request options, `prompt_cache_breakpoint` on content blocks; **cache writes surfaced as `input_token_details["cache_creation"]`**, reads stay `cache_read`, with `priority_`/`flex_` service-tier prefixed variants (verified 1.6.2 `base.py:4379-4445`); minimum openai SDK raised to 2.45 | …/langchain-openai%3D%3D1.3.5 |
| 1.4.0 | `reasoning_effort` standard param (#38887) | … |
| 1.4.1 | LangSmith gateway via env var (#38742) | … |
| 1.5.0 | openai SDK 3.0 supported (#39613) | …/langchain-openai%3D%3D1.5.0 |
| 1.5.1 / 1.5.2 | preserve streamed encrypted reasoning (#39635); preserve reasoning item boundaries (#39278); o-series token counting | … |
| 1.6.0 | standard `ModelError` exception types (#39538); clear error on unexpected response type in `_create_chat_result` (#39731) | …/langchain-openai%3D%3D1.6.0 |
| 1.6.1 / 1.6.2 | gpt-5.6-sol → Responses API; `reasoning_effort_levels` profile fixes; GPT-6 reasoning efforts | … |
Structured output: `with_structured_output` default `method="json_schema"` in both 0.3.34 and 1.6.2 (verified); your explicit `method="function_calling"` calls are unaffected.
`init_chat_model(..., streaming=True, stream_usage=True, max_retries=0, base_url=…)` kwargs all still accepted.

## 7. deepeval 4.0.7 / agentevals 0.0.9 / openevals 0.2.0
- **None pin `langchain-core`.** deepeval 4.0.7 has no langchain requirement at all (optional `deepeval.integrations.langchain.CallbackHandler`; `apps/api/eval` imports only `GEval`, `GPTModel`, `LLMTestCase`). agentevals → `openevals>=0.0.20`. openevals 0.2.0 → `langchain>=0.3.18`, `langchain-openai>=0.3.6`, `langsmith>=0.3.32` — no upper bounds.
- Their langchain imports (grepped site-packages): `BaseChatModel`, `BaseMessage`, `BaseMessageChunk`, `HumanMessage`, `convert_to_openai_messages`, `RunnableConfig`, `Runnable`, `init_chat_model` — all present in core 1.6.3 / langchain 1.4.1.
- `evalkit/` imports `langgraph.types.Command`, `agentevals.trajectory.match.create_trajectory_match_evaluator` — unchanged.
Sources: https://pypi.org/pypi/deepeval/4.0.7/json , https://pypi.org/pypi/agentevals/0.0.9/json , https://pypi.org/pypi/openevals/0.2.0/json .

## 8. Other providers

| pkg | from → to | change | source |
|---|---|---|---|
| langchain-anthropic | 1.4.7 → 1.7.2 | 1.5.5 **reasoning tokens reported in usage metadata** (#39590) → output-token totals/cost rows change; 1.5.3 unsupported fields stripped from system-message content blocks (#39101); 1.5.4 caller `tool_choice` preserved (#39206); 1.6.0 standard exception types; 1.6.1 invalid tool calls filtered from v1 content; 1.7.0 anthropic SDK 1.0 support, `container` param, `updates` thinking mode (#39962); 1.7.2 invalid tool-use blocks preserved (#40372) | https://github.com/langchain-ai/langchain/releases/tag/langchain-anthropic%3D%3D1.5.5 , …%3D%3D1.7.0 |
| langchain-google-genai | ≥4.0 → 4.4.0 | 4.2.2 `ContextOverflowError` on token limit (#1643); 4.2.4 google-genai SDK 2.x; 4.2.6 constructor thinking config; **4.3.0 default temperature removed for Gemini models (#1882)** + `reasoning_effort` (#1895); 4.3.5 standard exception types (#1952); 4.3.7 `__del__` that closed a shared client removed (#1963), foreign-provider reasoning blocks dropped (#1970); 4.4.0 agentic video | https://github.com/langchain-ai/langchain-google/releases/tag/libs%2Fgenai%2Fv4.3.0 , …%2Fv4.3.7 |

## 9. Risk list — grep / test before merging

1. **langgraph pin**: langchain 1.4.1 requires `langgraph>=1.2.11,<1.3` → pin explicitly; add `langgraph-checkpoint-postgres>=3.1.2`, `langgraph-checkpoint-sqlite>=3.1.1`.
2. **Injected-arg detection** (core #39602): run `tests/agents/` + PR #204's tool tests; diff `tool.tool_call_schema` / `get_input_schema()` for every tool in `app/tools/` — injected params hidden, model-facing params intact. Re-run #113/#125 cases (`ToolInvocationError` with empty `filtered_errors`).
3. **Chunk merge now raises** (core #39535): run streaming tests and `metrics.py` tests; `rg "AIMessageChunk\(" apps/api/tests apps/api/app` for hand-built chunks with bool fields.
4. **Strict/forward-ref tool schemas** (core #39306/#39570): `rg "strict=True|model_rebuild|ForwardRef" apps/api/app/tools`.
5. **Store namespace prefix** (checkpoint-postgres/sqlite #8478): audit `_namespace(...)` prefixes in `app/memory/store.py`; add a sibling-namespace isolation test.
6. **DeltaChannel/Overwrite** (langgraph 1.2.7–1.2.9): `rg "DeltaChannel|Overwrite" apps/api/app` — if 0, ignore.
7. **langchain-openai decision**: staying on 0.3.34 = unsupported combo (see §6a) — at minimum run `make test-docker` + `make eval-smoke` against a real OpenAI key. If moving to 1.6.2: lift the `<1.0` cap, `openai>=2.45`, and (a) add `StreamChunkTimeoutError` to `_RETRYABLE_LLM_NAMES` or decide `stream_chunk_timeout=None`; (b) `rg "callback_manager|\.predict\(|call_as_llm" apps/api` → must be 0; (c) usage rows may gain `cache_creation` and `priority_/flex_` keys.
8. **Usage-token deltas in eval baselines**: Anthropic reasoning tokens (1.5.5) and OpenAI cache_creation (1.3.5) change token totals → `make eval-check` baseline may need refresh.
9. **Gemini default temperature removed** (genai 4.3.0): any `google_genai` agent config without explicit temperature samples differently. `langchain-google-genai` is not installed locally — install it so `pip check`/tests exercise it.
10. **httpx2 via langsmith 0.12**: run `pip check` after install; confirm fastapi/starlette caps hold (CLAUDE.md forbids nudging them).
11. **Retry classification**: optionally switch `_is_retryable_llm` to `ModelError.is_retryable` (core 1.6) — only effective for providers ≥ core-1.6 releases.
12. Run `make test` and `make test-docker` (py3.12 image = production path for Postgres store/checkpointer).

## Items with "none found" (explicit)
- ToolNode / tools_condition / InjectedState / InjectedStore / ToolInvocationError.filtered_errors / `_infer_handled_types`: none in langgraph releases 1.2.7–1.2.11 (no prebuilt release).
- NodeError / RetryPolicy / Command / Send / interrupt / Runtime / get_runtime / context_schema / MessagesState / add_messages: none in langgraph 1.2.7–1.2.11.
- InMemoryStore TTL / index config, `search(limit, offset, query)` semantics: none in checkpoint 4.2.0 / langgraph 1.2.x notes.
- `BaseChatModel._generate` / `ChatResult` / `BaseCallbackHandler` / `DeterministicFakeEmbedding` / `InMemoryVectorStore`: none in core 1.4.9–1.6.3.
- langsmith becoming required / tracing defaults: none (already required at 1.4.8).
- deepeval / agentevals / openevals pins on langchain-core: none.
