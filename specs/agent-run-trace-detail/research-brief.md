# Research Brief — agent-run-trace-detail

Depth: **Deep** (intake lane `high-risk` → Deep per `rules/research-depth.md`; not re-scored).
External surface: **yes** — relies on version-specific APIs (langchain-core 1.4.8 callback
signatures, langgraph 1.2.6 task metadata, langchain-openai 0.3.34 `finish_reason` placement).
Waiver: none. Verified: 2026-09-03, against `design.md` as revised on 2026-09-03
(`Status: reviewed 2026-09-03`).

Builds on `specs/agent-turn-metrics/research-brief.md` — that brief's facts (callback propagation
into sub-graphs / `Send` / `ToolNode` / nested `llm.invoke()`, `stream_usage`, pricing table,
Alembic/`create_all` split, dashboard guard, FE tolerance) are **not** re-derived here. This brief
covers only what the step/trace feature adds: the tool hooks, node attribution for LLM steps,
`finish_reason`, hook ordering across threads, the prompt registry + prompt dashboard, and the
detail-page plumbing.

---

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **Build (thin, additive)** — extend `TurnMetricsHandler` with an ordered step list + the three tool hooks, add `agent_run_steps` + `agent_runs.prompt_versions`, and add one route/template to the existing dashboard router. Reuse `UUIDBase`, `Repo` dual-mode, `estimate_cost`, `_node_key`, `require_dashboard_access`, the `c7f1a9d4e6b2`/`e3b7c5d9a1f4` migration idiom, and `NotFoundError`. No new dependency, no node-code change. |
| **Why this is the lightest credible path** | Every field the design wants is already on a hook this app already receives: `on_tool_start` carries `metadata` with `langgraph_node`/`langgraph_checkpoint_ns` **and** `serialized["name"]`; `on_chat_model_start` carries the same metadata inside sub-graphs and `Send` workers; `finish_reason` reaches `response_metadata` on this app's exact streaming path. Nothing needs to be plumbed through node code. |
| **Confidence** | 82% — the architecture holds and the revised design already fixed the seq-at-start and content-boundary issues. Three design lines are contradicted by evidence and must be corrected in PLAN.md: (1) the prompt link `/dashboard/prompts/{name}` renders the **latest** version, not the recorded one; (2) `PROMPTS_FOR_NODE` keyed on the bare node name misattributes **every** sub-agent LLM call (they report `langgraph_node="assistant"`); (3) §3's "cannot drift from what actually shipped" is false for the six prompts baked at graph-build time. |
| **Next step** | `writing-plans`: fold the three corrections plus the `latency_ms is None` guard into PLAN.md; key prompt attribution on `_node_key(node, ns)`; link prompts as `/dashboard/prompts/{name}?version=v{N}`; put `tests/test_db_models.py` in the same task's `<files>` as the new model. |

---

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | Monorepo (pnpm + Turborepo): FastAPI API in `apps/api`, Next.js web in `apps/web` |
| Primary language + runtime | Python 3.14 locally (`.venv`), Python 3.12 in Docker |
| Frameworks / platforms | FastAPI 0.136.3, Starlette 1.2.1, SQLAlchemy 2 (`DeclarativeBase`/`Mapped`), Alembic (`render_as_batch=True`), Jinja2 dashboard, LangGraph 1.2.6, LangChain 1.x |
| Relevant packages | langchain-core 1.4.8, langchain-openai 0.3.34, langchain-anthropic 1.4.7, langgraph 1.2.6, langgraph-prebuilt 1.1.0, langfuse 4.12.0 (versions re-confirmed by `ls .venv/lib/python3.14/site-packages/*.dist-info` + `langchain_core-1.4.8.dist-info/METADATA`) |
| Detectable versions | as above; no new dependency required by this feature |
| Important constraints | `rules/behavior.md` (surgical, minimal); `rules/orchestration.md` (SUMMARY `### Verify` + `### Rollback`); stage/commit as separate commands; no Claude trailers (`CLAUDE.local.md`); `ruff-on-edit` strips imports added before their usage; `data-loss/migration` + `public-contract` hard gates already declared at intake; **the intake decision that no message text / tool arguments / model output is persisted is a fixed human decision, not a design variable** |

---

## Feature Understanding and Assumptions

- **Requested feature:** record the ordered per-step call chain of an agent turn (node / model /
  prompt name+version / tokens / cost / ms / tool name + status / `finish_reason`) into a new
  `agent_run_steps` table, add `agent_runs.prompt_versions`, and render `GET
  /dashboard/agent-runs/{id}` with a waterfall, per-model cost, a tool list, and prompt links.
- **What success appears to mean:** after one `/agent/chat` or `/agent/stream` turn, `agent_run_steps`
  holds one row per LLM call, per tool call and per node span, in start order; clicking a row on
  `/dashboard/agent-runs` opens a page that renders that chain; and a content-leak test proves no
  step field ever contains a message, a tool argument or model output.
- **Assumptions from the request:** `design.md` (revised 2026-09-03) stands. This brief supplies
  evidence, not new design forks. The no-content constraint is not re-litigated.
- **Assumptions still needing confirmation:** (a) whether the prompt link must open the *recorded*
  version (I assume yes — it is the stated purpose) or merely the prompt page; (b) whether
  `prompt_versions` should be captured at **graph build** rather than turn start, given that six
  of the eleven prompts are baked at build time.

---

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` (source) | `langchain_core/callbacks/base.py:409-424` — `on_tool_start(serialized, input_str, *, run_id, parent_run_id=None, tags=None, metadata=None, inputs=None, **kwargs)`: **it does carry `metadata`**. `:244-259` `on_tool_end(output, *, run_id, parent_run_id=None, **kwargs)`. `:261-275` `on_tool_error(error, *, run_id, parent_run_id=None, **kwargs)` — **no `metadata`, no `name`**. `:506-510` `raise_error=False`, `run_inline=False` defaults. |
| `Local` (source) | `langchain_core/tools/base.py:1041-1048` — `callback_manager.on_tool_start({"name": self.name, "description": self.description}, tool_input_str, ..., inputs=filtered_tool_input, tool_call_id=...)`. So `serialized["name"]` is **always** the tool name for any `BaseTool`. `:1338-1341` `_prep_run_args` passes `metadata=config.get("metadata")` into `run()`; `:1015-1022` `CallbackManager.configure(callbacks, self.callbacks, verbose, tags, self.tags, metadata, self.metadata)`; `callbacks/manager.py:1565-1577` forwards `metadata=self.metadata` and `parent_run_id=self.parent_run_id` to the handler. → **`on_tool_start` metadata contains `langgraph_node` / `langgraph_checkpoint_ns`.** |
| `Local` (source) | `langchain_core/tools/base.py:1098-1102` — `if error_to_raise: run_manager.on_tool_error(error_to_raise, tool_call_id=...); raise`; `:1103-1104` else `on_tool_end(output, color=color, name=self.name, **kwargs)` → `kwargs["name"]` is the tool name on **end** but not on **error**. `:1083-1093` a `ToolException` is converted to content with `status="error"` **only when `self.handle_tool_error` is set on the tool** — then `on_tool_end` fires, not `on_tool_error`. `:1358-1390` `_format_output` returns a `ToolMessage(... status=status)`. |
| `Local` | `app/agents/subagents/_base.py:240-248` — `handle_tool_errors` is set on **`ToolNode`**, never on a tool (`grep handle_tool_error` over `app/tools/` returns only a docstring). ToolNode catches *outside* `BaseTool.run`, so `on_tool_error` fires for every tool failure in this app today. |
| `Local` (source) | `langgraph/prebuilt/tool_node.py:958 / :1105` — `tool.invoke(call_args, config)` / `await tool.ainvoke(call_args, config)`; the `config` is the ToolNode task's own config → callbacks **and** metadata reach the tool. |
| `Local` (source) | `langgraph/_internal/_runnable.py:400-427` — `RunnableCallable.invoke` calls `callback_manager.on_chain_start(None, input, name=config.get("run_name") or self.get_name(), run_id=config.pop("run_id", None))`, then `child_config = patch_config(config, callbacks=run_manager.get_child())`, then `on_chain_end(ret)` / `on_chain_error(e)`. **`serialized` is `None` for every langgraph node run** — the node name is only in `kwargs["name"]` and `metadata["langgraph_node"]`. `parent_run_id` of a ToolNode-executed tool is therefore the ToolNode task's chain run. |
| `Local` (source) | `langgraph/pregel/_algo.py:653-659` (PULL task) and `:1006-1011` (PUSH / `Send` task) both set `{"langgraph_step", "langgraph_node", "langgraph_triggers", "langgraph_path", "langgraph_checkpoint_ns"}`; `:624` `task_checkpoint_ns = f"{checkpoint_ns}{NS_END}{task_id}"`, `:615-624` `checkpoint_ns = f"{parent_ns}{NS_SEP}{name}"` → a sub-graph node's ns is `concierge:<id>|assistant:<id>`; `:696,:746` propagate `task_checkpoint_ns` as the child graph's parent ns. |
| `Local` (source) | `langchain_core/language_models/chat_models.py:741-743` — `inheritable_metadata = {**(config.get("metadata") or {}), **self._get_ls_params_with_defaults(...)}` → **`on_chat_model_start` metadata = the langgraph task metadata + `ls_model_name`**, inside sub-graphs and `Send` workers alike. `:757-765` `on_chat_model_start(self._serialized, [...], ...)`. `on_llm_end` has **no** `metadata` kwarg (`callbacks/base.py:90`). |
| `Local` (source) | `langchain_openai/chat_models/base.py:908-914` — streaming: `generation_info["finish_reason"] = choice["finish_reason"]` (plus `model_name`, `system_fingerprint`, `service_tier` on the same chunk); `:1259-1263` — non-streaming: same key in `generation_info`. `langchain_core/language_models/chat_models.py:2011-2013,2168-2170` — `generation.message.response_metadata = _gen_info_and_msg_metadata(generation)`; `:2677-2683` that merges `generation_info` into `response_metadata`. `:206-232` `generate_from_stream` builds a `ChatResult` with **`llm_output=None`** → on this app's path (`ChatOpenAI(streaming=True)`, `_agenerate` → `agenerate_from_stream`) `response_metadata` is the **only** source of both `model_name` and `finish_reason`. `:963-970` the `astream()` path calls `on_llm_end(LLMResult(generations=[[merged chunk]]))` — same field, also present. |
| `Local` (source) | `langchain_core/callbacks/manager.py:303-312` — sync `handle_event` calls `getattr(handler, event_name)(*args, **kwargs)` **inline on the emitting thread**; `:471-487` async `ahandle_event` awaits `run_inline=True` handlers **sequentially on the loop thread first**, then `asyncio.gather`s the rest. `:428-437` non-inline sync handlers go through `run_in_executor`. |
| `Local` (source) | `langgraph/_internal/_runnable.py:544-553` — a **sync** node callable is wrapped as `partial(run_in_executor, None, thing)`; `langgraph/pregel/_executor.py:120-172` `AsyncBackgroundExecutor` runs async tasks as asyncio tasks on one loop. → hooks genuinely fire from **several threads**; a lock-guarded counter is required, not optional. |
| `Local` | `app/agents/metrics.py` — `TurnMetricsHandler(run_inline=True, raise_error=False)`; `_node_key(node, checkpoint_ns)` already collapses a sub-graph ns to `"<ns_root>/<node>"`; `_seen_ns` dedupes nested runs; `on_chat_model_start` today records **only** `(start, ls_model_name)` — no node/ns; `snapshot()`/`public()` shapes are the ones the design must leave untouched. |
| `Local` | `app/routers/agent.py:278-279` — `metrics = TurnMetricsHandler()` then `started = time.monotonic()` on the next statement (so `_created ≈ started`); `:297-311` `_finalize` → `metrics.close(started)`, `estimate_cost(...)`, `AgentRunRepository(session).finish(...)`, then an explicit `session.commit()`. `app/streaming/agent_run.py` — the stream finalizer runs `metrics.close_if_open()` (which uses `_created`) then `AgentRunRepository(session_factory).finish(...)` on the isolated factory, inside `finally`. Both are exactly where `add_steps` belongs. |
| `Local` | `app/routers/dashboard_prompts.py:118-123` — `@router.get("/prompts/{name}")` → `_render_detail(request, name, version)`; `:66-70` `selected = latest` **when `version is None`**; `:37-43` `_parse_version` accepts `"3"` or `"v3"` → the version-pinned URL is `/dashboard/prompts/{name}?version=v{N}`. `:26-32` the router carries `dependencies=[Depends(require_dashboard_access)]` and `include_in_schema=False`, same as `dashboard.py:65-70`. |
| `Local` | `app/prompts/registry.py:77-101` — `names() -> list[str]` (sorted), `versions(name)`, `active_version(name) -> int` (falls back to `max(versions)` when `active.yaml` omits the name), `get(name, version=None)`; module singleton `registry`. `app/prompts/active.yaml` — 11 names: `communication_style:8, supervisor:9, concierge:11, planner:11, journal:2, booking:7, budget:2, reflection:1, memory_extraction:5, date_resolution:1`. |
| `Local` | Call-time vs build-time prompt reads: **call time** — `app/agents/supervisor.py:232`, `app/agents/nodes.py:218` (reflection), `app/tools/date_tools.py:96` (`date_resolution`), `app/memory/extractor.py:118` (`memory_extraction`, background). **Build time** — `app/agents/subagents/{concierge.py:26, planner.py:26, journal.py:22, booking.py:27, budget.py:22}` and `_base.py:206` (`communication_style`), all evaluated when the graph is built. |
| `Local` | Nodes that call an LLM under a prompt that is **not** in the registry: `summarize` (`app/memory/summarizer.py:84`, module constant `_SUMMARY_SYSTEM`) and `synthesize` (`app/agents/nodes.py:169`, inline `SystemMessage`). |
| `Local` | Node names actually seen as `langgraph_node`: root graph `pii_guardrail, load_context, summarize, supervisor, plan, planner, concierge, journal, booking, budget, synthesis_worker, synthesize, reflection` (`app/agents/graph.py:131-169`); sub-graph inner `assistant, tools, trip_guard` (`app/agents/subagents/_base.py:235,240-255`). `ALL_SUBAGENTS = ("planner","concierge","journal","booking","budget")` (`app/agents/constants.py:23-29`). |
| `Local` | `app/repositories/agent_run.py` — `Repo` subclass; `start`/`finish`/`add_background` each `with self._session() as s: ... self._commit(s)`; `_FINISH_METRIC_KEYS` is the allowlist `finish` maps onto columns (unknown keys ignored); `finish` on a missing id logs a warning and returns. `app/repositories/base.py:22-70` — dual mode: live `Session` → `flush`; `sessionmaker` → `commit`. |
| `Local` | `app/db/models/agent_run.py` — `UUIDBase`, String ids, **no FKs**, `JSON` via generic `sqlalchemy.JSON` for `by_model`/`by_node`. `app/db/models/__init__.py` — every model is imported and listed in `__all__`; `alembic/env.py` relies on this import to register tables. |
| `Local` | Alembic: computed over all 14 revisions in `alembic/versions/`, there is exactly **one head, `e3b7c5d9a1f4`** (`add_agent_runs`, `down_revision = c7f1a9d4e6b2`) and **no branch points** → design §4.3's `down_revision = e3b7c5d9a1f4` is correct. |
| `Local` | `app/core/lifespan.py:35-37` — `create_all` only when `engine.dialect.name == "sqlite"`. `tests/conftest.py:59,102,111` — `Base.metadata.create_all(get_engine(tmp_db), checkfirst=True)` in three fixtures. `tests/test_db_models.py:5-32` asserts the **exact** table set (`agent_runs` present) and `test_agent_runs_columns` the exact column set → both break on this change. |
| `Local` | `app/core/dashboard_auth.py` — Basic creds configured → 401 challenge on mismatch; no creds + production → `NotFoundError` (404); no creds + dev → open. `app/exceptions.py:38-42` `NotFoundError.status_code = 404`, already raised from `dashboard_prompts` → the 404 idiom for an unknown run id is established. |
| `Local` | `app/core/pricing.py:81-108` `estimate_cost(by_model)` — returns `None` if `by_model` is empty **or any** model normalises to a name absent from the price table; otherwise `(input-cached)*p_in + cached*p_cached + output*p_out) / 1e6`. Called with a single-model dict it yields exactly the design's per-step semantics — reuse it. |
| `Local` | `app/routers/dashboard.py:1021-1051` `@router.get("/agent-runs")` + `app/templates/agent_runs.html:56-81` — the `started` cell is a plain `<span>`; adding `/agent-runs/{id}` after the list route is unambiguous (no path conflict). Existing precedent for a `{param}` sibling: `agent-config` / `agent-config/{agent_name}` (`dashboard.py:905,925`). |
| `Upstream` | **Langfuse observation model** — one flat `observations` table per trace; ten observation types incl. `span`, `generation`, `tool`, `agent`, `retriever`, `guardrail`; each row carries name, parent, start/end time, model, `usageDetails`, cost, level, status, metadata, **and `input`/`output` as separate dedicated fields**. Langfuse docs: "Langfuse stores one observations table, and each row holds the observation-level data plus a copy of the trace-level attributes" — kept flat "to keep queries and aggregations fast". Same shape as `agent_run_steps`; this design simply omits the two content columns. |
| `Upstream` | **MLflow LangGraph tracing** and the Last9 OTel LangChain/LangGraph guide both persist per-span token usage + latency and aggregate cost/time trends in a built-in dashboard from exactly the callback stream this app already has — no node-code instrumentation. |
| `Docs` | **OpenTelemetry GenAI semantic conventions** (the canonical "structure without content" precedent): `gen_ai.operation.name` and `gen_ai.provider.name` **Required**; `gen_ai.request.model` conditionally required; `gen_ai.response.model`, `gen_ai.response.finish_reasons`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` **Recommended**; `error.type` conditionally required on failure; `gen_ai.tool.name` on the execute-tool span. `gen_ai.input.messages` / `gen_ai.output.messages` are marked **Opt-In** with the warning that they are "likely to contain sensitive information including user/PII data", gated by `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` and carried **separately** from the always-on attributes. |
| `Docs` | **LangSmith / Langfuse masking** — the mainstream answer to the same question is a *masking* switch over a schema that stores content (`LANGSMITH_HIDE_INPUTS` / `LANGSMITH_HIDE_OUTPUTS` / `hide_metadata`, Langfuse `mask=`), i.e. content-by-default plus redaction. This spec's choice (never write the columns) is strictly stronger and needs no redaction correctness argument. |
| `Inference` | Because `on_tool_error` receives neither `metadata` nor `name`, a `run_id`-keyed open-step map is **required** for tool steps — the same shape `metrics.py` already uses for LLM runs. Not executed, read from the signatures. |
| `Inference` | `seq` assigned at step start (revised design §4.1) makes `seq` order == `offset_ms` order even across threads, because both are taken under the same lock at the same moment. Ordering the page by `(offset_ms, seq)` is therefore equivalent and tolerates a future reordering of `seq`. Reasoned from `manager.py` + the design, not executed. |

---

## Local Findings

- **Relevant files, modules, scripts, docs, tests:** `app/agents/metrics.py` (the handler to extend),
  `app/agents/graph.py`, `app/agents/subagents/_base.py`, `app/agents/constants.py`,
  `app/agents/supervisor.py`, `app/agents/nodes.py`, `app/agents/retry.py`,
  `app/memory/summarizer.py`, `app/tools/date_tools.py`, `app/prompts/registry.py` +
  `app/prompts/active.yaml`, `app/routers/agent.py` (`_config`, `_finalize`),
  `app/streaming/agent_run.py`, `app/repositories/{base,agent_run}.py`,
  `app/db/models/{agent_run,__init__}.py`, `app/db/base.py`, `alembic/env.py` +
  `alembic/versions/e3b7c5d9a1f4_add_agent_runs.py` (head + template),
  `app/routers/{dashboard,dashboard_prompts}.py`, `app/core/{dashboard_auth,pricing,lifespan}.py`,
  `app/exceptions.py`, `app/templates/{agent_runs,prompt_detail,base}.html`,
  `tests/conftest.py`, `tests/test_db_models.py`. Target test dirs all exist:
  `tests/agents/`, `tests/db/`, `tests/repositories/`, `tests/api/agent_config/`.
- **Existing abstractions or extension points:** `TurnMetricsHandler` hook set + `_node_key` +
  `_seen_ns` dedupe; `Repo._session()`/`_commit()` dual mode; `estimate_cost`; `UUIDBase`;
  `require_dashboard_access` declared at **router** level on both dashboard routers;
  `NotFoundError` → 404; `Jinja2Templates` + the `fmt_cost`/`fmt_ms`/`hm` filters already used by
  `agent_runs.html`; `registry.names()` / `active_version()`; `_parse_version` on the prompt page.
- **Conventions worth preserving:** String ids, no FKs; ISO-string timestamps; generic
  `sqlalchemy.JSON`; `op.batch_alter_table` in revisions with a docstring stating additive vs
  destructive; repositories log-and-return rather than raise on a missing row; every hook body
  wrapped so it cannot raise; dashboard pages `include_in_schema=False`; comments explain *why*.
- **What can likely be reused:** `estimate_cost` per step (single-model dict); `_node_key` for
  prompt/node attribution; `e3b7c5d9a1f4` as the migration template; `AgentRunRepository` shape for
  `add_steps`/`steps_for`; `dashboard_prompts._parse_version` semantics for the version-pinned link;
  `agent_runs.html` markup idiom for the detail page.
- **What appears missing locally:** no step table; `on_tool_*` hooks are unimplemented;
  `on_chat_model_start` does not record node/ns today; there is no node→prompt map; there is no
  version-pinned prompt link anywhere in the templates; `summarize` and `synthesize` prompts are
  not in the registry at all, so no version can be recorded for them.

---

## Upstream Findings

- **Repositories inspected / pages checked:** Langfuse observability data-model and
  observation-types docs; Langfuse LangGraph cookbook + LangChain integration page; MLflow
  LangGraph tracing integration; Last9 "Instrument LangChain and LangGraph Apps with
  OpenTelemetry"; the LangSmith mask-inputs-outputs guide and `langchain-ai/langsmith-pii-removal`.
- **Pattern or capability already present upstream:** one **flat** per-step table keyed by run id
  with a `type`/`kind` discriminator, start/end timestamps, model, usage and cost, level/status and
  a metadata blob — rendered as a timeline by ordering on start time and nesting by parent. Content
  lives in **dedicated** `input`/`output` fields, which is precisely what makes "structure without
  content" expressible as *omitting two columns* rather than filtering every field.
- **Files, modules, or areas worth modeling:** Langfuse's observation row (name, parent, start/end,
  model, usageDetails, costDetails, level, statusMessage, metadata) as the column checklist;
  OTel GenAI's attribute set as the "what is safe to always record" checklist.
- **How closely the upstream pattern matches this repo:** very closely. `agent_run_steps` is a
  Langfuse observation row minus `input`/`output`, plus a prompt pointer that Langfuse expresses as
  a linked prompt version. The one structural difference is deliberate: this design keeps the list
  **flat and ordered by start** and indents by namespace instead of storing a parent pointer — an
  acceptable simplification at this depth, and it is what makes `seq`-at-start load-bearing.
- **Any upstream gaps or uncertainties:** no upstream project was found that persists a *content-free*
  step table into its own application database — every one either stores content behind a masking
  switch (LangSmith, Langfuse) or defers to an external tracer. So the closest precedent for the
  no-content decision is a **specification** (OTel GenAI's opt-in gate), not an implementation.
  Search for an in-repo `agent_run_steps`-style table returned only blog posts; labelled here rather
  than modelled.

---

## Docs Findings

- **Official sources checked:** OpenTelemetry GenAI semantic conventions (`gen-ai-spans`, now in
  `open-telemetry/semantic-conventions-genai`; the `opentelemetry.io/docs/specs/semconv/gen-ai/`
  page is a redirect stub and no longer maintained); `opentelemetry.io/blog/2026/genai-observability/`;
  `langfuse.com/docs/observability/data-model` and `.../features/observation-types`;
  `docs.langchain.com/langsmith/mask-inputs-outputs`. Installed source was read directly for
  langchain-core 1.4.8, langchain-openai 0.3.34, langgraph 1.2.6 (version-matched).
- **Version-matched vs latest-stable status:** all langchain/langgraph facts are read from the
  installed 3.14 site-packages, so they are version-matched to what runs here. OTel GenAI semconv
  and the Langfuse/LangSmith pages are latest-stable — they are used as *design precedent*, not as
  an API this code calls, so the version mismatch is immaterial.
- **Built-in capabilities that already support the feature:** `BaseCallbackHandler`'s three tool
  hooks (already routed to this app's handler list, unimplemented); LangGraph task metadata on
  PULL and PUSH tasks; `response_metadata["finish_reason"]`; `run_inline` for ordering;
  `AIMessage.usage_metadata` (already consumed).
- **Current recommended APIs or workflows:** read the tool name from `serialized["name"]`; read
  node attribution from each hook's own `metadata`, not from `parent_run_id`; read
  `finish_reason`/`model_name` from `generations[0][0].message.response_metadata` (**not** from
  `LLMResult.llm_output`, which is `None` on the streaming path this app uses).
- **Important caveats, deprecations, or migration notes:** `gen_ai.prompt` / `gen_ai.completion`
  are deprecated upstream in favour of `gen_ai.input.messages` / `gen_ai.output.messages`, both
  Opt-In — reinforcing that content belongs behind a gate, and that a design which stores neither
  needs no gate. `on_tool_error` carries no `name` and no `metadata`, so it cannot be handled
  standalone. The async `CallbackManager.on_tool_start` (`manager.py:2095-2106`) does **not**
  forward `inputs=` while the sync one does — irrelevant here only because both are ignored, but
  it means a test must not rely on `inputs` being present on the async path.

---

## Recommendation

- **Primary recommendation:** **Build (thin, additive)** exactly as `design.md` (revised) specifies,
  with the three corrections in §Risks folded into PLAN.md. No new dependency, no node-code change,
  no change to `snapshot()`/`public()`.
- **Why this is the lightest credible path:** every datum the page needs is already on a hook this
  app receives, on the exact library versions installed — `serialized["name"]` for the tool,
  each hook's own `metadata` for node+ns (PULL *and* `Send` *and* sub-graph),
  `response_metadata["finish_reason"]` on this app's streaming path, and a single `run_id`-keyed
  open-step map for durations. Persistence rides the two existing `finish()` call sites, so the
  agent-turn-metrics deadlock cannot recur; `estimate_cost`, `_node_key`, `UUIDBase`, `Repo` and
  the router guard are all reused verbatim. The migration is one additive revision off a single
  clean head.
- **Why the next-best alternative lost:** (a) *store content behind a masking switch* — the
  mainstream upstream pattern (LangSmith/Langfuse) — was ruled out by the human at intake and would
  reverse the #118/#129 PII posture; it also imports a redaction-correctness burden this design does
  not have. (b) *Reconstruct the chain from Langfuse* — opt-in, external, and the operator dashboard
  should stand on its own data. (c) *Wrap nodes / thread a recorder through node code* — touches 13
  root nodes plus 5 sub-agent builders and still misses structured-output and tool calls, which the
  callback stream gets for free.
- **What would change this recommendation:** if the page turned out to need a genuine parent/child
  tree (rather than ns-indentation) at scale, a `parent_run_id` column would be cheaper to add now
  than to backfill later — but the evidence says the flat, start-ordered list is sufficient at this
  depth. If per-tool `handle_tool_error` were ever adopted, the `on_tool_end` status read below
  becomes mandatory rather than defensive.

---

## Risks, Unknowns, and Follow-Up Questions

### Design lines contradicted by evidence

1. **§1 and §4.5 — the prompt link shows the wrong version.**
   Design §1: *"linking to the prompt text already published at `/dashboard/prompts/{name}`"*;
   §4.5.5: *"**Prompts used** — from `prompt_versions`, each linking to `/dashboard/prompts/{name}`."*
   **Contradicted.** `app/routers/dashboard_prompts.py:118-123` → `_render_detail(request, name, None)`
   → `:66-70` `if version is None: selected = latest`. The bare URL renders the **latest** version,
   not the recorded one, so as soon as anyone adds `v12.md` to `concierge/` the detail page silently
   shows a prompt the turn never ran under — which defeats the feature's stated purpose ("the exact
   prompt versions used"). **Fix:** link `/dashboard/prompts/{name}?version=v{N}`;
   `_parse_version` (`:37-43`) already accepts `"12"` and `"v12"`, and an unknown version raises
   `NotFoundError` → 404, so no route change is needed.

2. **§4.2 — `PROMPTS_FOR_NODE` keyed on the bare node name misattributes every sub-agent LLM call.**
   Design §4.2: *"a static map from node name to the **list** of prompts … A test asserts the map's
   keys exactly equal the graph's node set."*
   **Contradicted.** A sub-agent's LLM call happens in the sub-graph's `assistant` node
   (`app/agents/subagents/_base.py:235`), so `metadata["langgraph_node"] == "assistant"` for the
   concierge, planner, journal, booking **and** budget calls alike; the sub-agent identity exists
   only in `langgraph_checkpoint_ns` (`concierge:<id>|assistant:<id>`, `_algo.py:615-624`). Keyed on
   the bare name, all five collapse onto one entry. Symmetrically, "the graph's node set" (the 13
   root nodes) neither contains `assistant`/`tools`/`trip_guard` — which *do* appear — nor excludes
   root nodes that never emit an LLM step. **Fix:** key the map on `_node_key(node, ns)` — the
   function `metrics.py:31-45` already provides, yielding `"concierge/assistant"` — and assert the
   map against `ALL_SUBAGENTS` (`constants.py:23`) plus the root node list, not "the graph's node set".

3. **§3 — "cannot drift from what actually shipped" is false for six of the eleven prompts.**
   Design §3: *"Recording `name -> version` is therefore smaller than the text, **cannot drift from
   what actually shipped**"*; §4.2: *"captured once per turn … Complete and drift-proof."*
   **Contradicted for the build-time reads.** `communication_style` (`_base.py:206`) and the five
   sub-agent prompts (`concierge.py:26`, `planner.py:26`, `journal.py:22`, `booking.py:27`,
   `budget.py:22`) are resolved when the graph is **built**, not per turn; only `supervisor`
   (`supervisor.py:232`), `reflection` (`nodes.py:218`), `date_resolution` (`date_tools.py:96`) and
   `memory_extraction` (`extractor.py:118`) are read at call time. A `registry.reload()` (or an
   `active.yaml` edit picked up by a re-instantiated registry) without a graph rebuild therefore
   makes a turn-start snapshot record a version the running graph is not using — the exact failure
   mode recorded in `prompt-changes-need-graph-rebuild-not-hot-reloaded`. **Fix:** either capture
   `prompt_versions_snapshot()` once at graph build and hand it to the router, or keep the turn-start
   capture and downgrade §3's claim to "cannot drift *for call-time prompts*; the baked six are
   accurate as long as the process has not reloaded the registry without rebuilding the graph".

### Technical risks (not contradictions)

4. **`on_tool_end` can carry a failure that `on_tool_error` never reports.** Today every tool
   failure in this app reaches `on_tool_error`, because `handle_tool_errors` is on `ToolNode`
   (`_base.py:240-248`) and catches *outside* `BaseTool.run`, which fires `on_tool_error` first
   (`tools/base.py:1098-1100`). But a tool that sets its own `handle_tool_error` converts the
   exception to a `ToolMessage(status="error")` and fires **`on_tool_end`** instead
   (`tools/base.py:1083-1093`, `:1358-1390`) — which this design would record as `status="ok"`.
   Cheap hardening that stays inside the content boundary: on `on_tool_end`, read
   `getattr(output, "status", None) == "error"` (a two-valued enum, never content) and record
   `status="error"`. Add a test so a future per-tool handler cannot silently mislabel.

5. **`design.md`'s rationale for ignoring `parent_run_id` is inaccurate (the conclusion is right).**
   §4.1: *"`parent_run_id` is *not* usable, because `on_chain_start` registers only the outermost run
   per namespace, so a tool's immediate parent is normally absent."* In fact a ToolNode-executed
   tool's `parent_run_id` **is** the ToolNode task's own chain run (`_runnable.py:402-409`,
   `tool_node.py:958`), and that task *is* the outermost run for ns `…|tools:<task_id>`, so it would
   normally be present. Using each hook's own `metadata` is still the better choice — simpler,
   uniform with the LLM path, and immune to future nesting changes — but PLAN.md should not carry a
   false justification.

6. **`latency_ms` may be `None`, and the waterfall divides by it.** §4.5.2 computes bar offsets as
   "percentages of the turn's latency". `agent_runs.latency_ms` is nullable and `close()` /
   `close_if_open()` can both be missed on a hard failure. Guard the denominator (fall back to
   `max(offset_ms + ms)` across the steps, or render bars only when a positive latency exists).
   Related, minor: §4.3's "one clock throughout" holds only because `agent.py:278-279` constructs
   the handler one statement before `started = time.monotonic()` — `close(started)` uses the router's
   origin while `offset_ms` uses `_created`. The delta is microseconds; it is worth a comment so a
   later reordering of those two lines does not quietly skew the bars.

7. **`finish_reason` is absent offline.** `FakeLLM` emits no `response_metadata`, and on the real
   path `LLMResult.llm_output` is `None` (`generate_from_stream`, `chat_models.py:206-232`), so
   `response_metadata` is the sole source of both `model_name` and `finish_reason`. Tests must assert
   `finish_reason is None` offline rather than asserting a value, and the handler must not skip an
   otherwise-valid step because `finish_reason` is missing.

8. **Two LLM-calling nodes have no recordable prompt at all.** `summarize`
   (`app/memory/summarizer.py:84`, module constant) and `synthesize` (`app/agents/nodes.py:169`,
   inline `SystemMessage`) build system prompts that are not in the registry, so they map to `[]` and
   the page answers "prompt system là gì" with nothing for those steps. That is honest, not a bug —
   but it should be stated in `SUMMARY.md` rather than discovered on the page. Moving them into the
   registry is out of scope here.

9. **Exact-shape tests break.** `tests/test_db_models.py:5-32` asserts the exact table set and
   `test_agent_runs_columns` the exact `agent_runs` column set; both must be updated in the **same**
   task as the model, and the new model must be added to `app/db/models/__init__.py` (import **and**
   `__all__`) or neither `create_all` (`lifespan.py:37`, `conftest.py:59/102/111`) nor `alembic/env.py`
   will see the table.

10. **Volume cap interacts with the open-step map.** §4.1's `MAX_STEPS_PER_TURN = 200` stops
    *opening* new steps. The end hooks must then tolerate a `run_id` with no open step (drop
    silently, do not create a step at close), or the cap leaks close-only rows with no `offset_ms`.

### Evidence gaps

- No live run was executed (read-only session): every claim here is from installed source, repo
  source, or a fetched doc page. In particular the *actual* interleaving of concurrent
  `synthesis_worker` `Send` workers' hooks was reasoned from `_executor.py` + `manager.py`, not
  observed.
- Whether the running graph's `assistant` node reports `ls_model_name` identical to the model the
  step should be priced under was not re-verified here — it is inherited from the parent brief.
- `apps/web` was not inspected; this feature adds no FE surface.
- The Langfuse observation **field list** came from the observation-types page, which does not
  enumerate the full schema; the enumeration above is partly from its code examples. The API
  reference (`api.reference.langfuse.com`) was not fetched.

### Version uncertainties

- OTel GenAI semconv has *moved repositories*; the `opentelemetry.io` page is now a stub. The
  attribute list above is from the new repo's `gen-ai-spans.md` at HEAD (unversioned) — used as
  precedent only.
- Python 3.12 (Docker) vs 3.14 (local): no API in scope differs, but the Alembic round-trip test
  should run under `make test-docker` as well, per `docker-py312-vs-local-py314`.

### Follow-up questions for the user (max 2)

1. Should the prompt link pin the recorded version (`?version=v{N}`) — my strong recommendation —
   or is the un-pinned "current prompt" page the intended destination?
2. Should `prompt_versions` be captured at **graph build** (accurate for all eleven, including the
   six baked prompts) instead of at turn start, or is the turn-start capture plus a documented
   caveat acceptable?

---

## Source Pack

- **Local files read:** `.claude/skills/xia2/SKILL.md`,
  `.claude/skills/xia2/references/research-brief-template.md`,
  `.claude/skills/xia2/references/depth-classifier.md`, `.claude/rules/research-depth.md`,
  `.claude/rules/{architecture,orchestration,guidelines,behavior,terminology,auto-correct-scope}.md`
  (via context injection), `CLAUDE.md`, `CLAUDE.local.md`,
  `specs/agent-run-trace-detail/{SUMMARY.md,design.md}`,
  `specs/agent-turn-metrics/research-brief.md`,
  `apps/api/app/agents/metrics.py`, `apps/api/app/agents/graph.py` (grep),
  `apps/api/app/agents/subagents/_base.py`, `apps/api/app/agents/subagents/{concierge,planner,journal,booking,budget}.py` (grep),
  `apps/api/app/agents/{constants,supervisor,nodes,retry}.py` (grep + excerpts),
  `apps/api/app/memory/{summarizer,extractor}.py` (grep), `apps/api/app/tools/date_tools.py` (grep),
  `apps/api/app/prompts/registry.py`, `apps/api/app/prompts/active.yaml`,
  `apps/api/app/routers/agent.py` (grep + excerpts), `apps/api/app/routers/dashboard.py` (grep + excerpts),
  `apps/api/app/routers/dashboard_prompts.py`, `apps/api/app/streaming/agent_run.py`,
  `apps/api/app/repositories/{base,agent_run}.py`, `apps/api/app/db/models/{agent_run,__init__}.py`,
  `apps/api/app/core/{dashboard_auth,pricing,lifespan}.py` (excerpts), `apps/api/app/exceptions.py` (excerpt),
  `apps/api/app/templates/agent_runs.html` (grep), `apps/api/tests/conftest.py` (grep),
  `apps/api/tests/test_db_models.py`, `apps/api/alembic/versions/*.py` (full revision-graph scan).
  Installed sources: `langchain_core/callbacks/{base,manager}.py`,
  `langchain_core/tools/base.py`, `langchain_core/language_models/chat_models.py`,
  `langchain_openai/chat_models/base.py`, `langgraph/pregel/{_algo,_runner,_executor}.py`,
  `langgraph/_internal/_runnable.py`, `langgraph/prebuilt/tool_node.py`.
- **Upstream repositories or pages checked:**
  https://langfuse.com/docs/observability/data-model ;
  https://langfuse.com/docs/observability/features/observation-types ;
  https://langfuse.com/guides/cookbook/integration_langgraph ;
  https://mlflow.org/docs/latest/genai/tracing/integrations/listing/langgraph ;
  https://last9.io/blog/langchain-and-langgraph-instrumentation-guide/ ;
  https://github.com/langchain-ai/langsmith-pii-removal ;
  web search "LangGraph persist per-step trace table waterfall dashboard callback handler
  on_tool_start database schema" (returned tracing-vendor material only; no in-repo step-table
  implementation found).
- **Official docs domains or pages checked:**
  https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md ;
  https://opentelemetry.io/blog/2026/genai-observability/ ;
  https://docs.langchain.com/langsmith/mask-inputs-outputs ;
  https://langfuse.com/docs/observability/data-model
  (redirect stub, no longer maintained: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/).

---

## Evidence Boundary

> **Confirmed from artifacts:** every langchain-core 1.4.8 / langchain-openai 0.3.34 / langgraph
> 1.2.6 claim above, read from the installed source in `.venv/lib/python3.14/site-packages/` with
> file:line references — the `on_tool_start`/`on_tool_end`/`on_tool_error` signatures,
> `serialized == {"name", "description"}`, `metadata=config.get("metadata")` reaching the tool's
> callback manager, `parent_run_id` being the enclosing node chain run, `serialized is None` for
> langgraph node chain runs, `langgraph_node`/`langgraph_checkpoint_ns` on both PULL and PUSH tasks
> and their sub-graph nesting, `inheritable_metadata` on `on_chat_model_start`, `on_llm_end` having
> no `metadata`, `finish_reason` landing in `generation_info` → `response_metadata`,
> `LLMResult.llm_output is None` under `generate_from_stream`, sync `handle_event` running inline on
> the emitting thread, `run_inline` handlers being awaited sequentially first, and sync node
> callables being wrapped into `run_in_executor`. Repo facts likewise read from source: the prompt
> registry API, `/dashboard/prompts/{name}` defaulting to *latest*, the router-level
> `require_dashboard_access`, `NotFoundError` → 404, `Repo` dual mode, `estimate_cost` semantics,
> `create_all` sites, the exact-shape tests, the build-time vs call-time `registry.get` split, the
> sub-agent inner node names, and the single Alembic head `e3b7c5d9a1f4` (computed over all 14
> revisions; no branch points).
> **Inferred from patterns:** that `seq`-at-start makes `seq` and `offset_ms` agree across threads;
> that a `run_id`-keyed open-step map is required because `on_tool_error` carries neither `name` nor
> `metadata`; that the volume cap needs a tolerant close path; that a future per-tool
> `handle_tool_error` would silently report `ok`; the Langfuse observation field list (partly from
> doc code examples, not a schema page).
> **Not checked:** no test or server was run (read-only session) — no claim here is a re-run
> behaviour; the actual hook interleaving of concurrent `Send` workers; the Langfuse API reference
> schema; `apps/web` (no FE surface in scope); whether `ls_model_name` inside a sub-agent matches the
> pricing key (inherited unverified from the parent brief); the OTel GenAI semconv version, since
> the specification is unversioned at HEAD and used only as precedent.
