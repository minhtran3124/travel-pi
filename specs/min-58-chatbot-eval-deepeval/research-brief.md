# Research Brief — MIN-58 DeepEval + G-Eval Offline Eval Harness

**Depth mode:** Deep (new external SDK `deepeval` + new dependency in `requirements-ai.txt`; provider-agnostic LLM-as-judge integration).
**Config note:** `.claude/skills/xia2/PROJECT.md` is **stale** — it describes the harness-skills meta-repo (root `hooks/`, `scripts/run-tests.sh`, `skills/`), none of which exist in travel-pi (they live under `.claude/`). Depth was set from project-agnostic signals, not those mappings. **Backlog:** run `/bootstrap-xia2` to regenerate PROJECT.md for the travel-pi (FastAPI) stack.

---

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **Adapt upstream (DeepEval) + build a thin adapter layer.** Add `deepeval` as an eval-only dep; wrap the existing `get_llm()` provider-agnostic client in a `DeepEvalBaseLLM` grader; drive the compiled LangGraph graph directly (not `create_agent`) to build `LLMTestCase`s. Layer alongside the existing no-network routing smoke. |
| **Why this is the lightest credible path** | DeepEval's `GEval`, `ToolCorrectnessMetric`, `AnswerRelevancyMetric`, `HallucinationMetric` cover every criterion in the ticket out of the box, and its `DeepEvalBaseLLM` extension point maps 1:1 onto the repo's `init_chat_model()` client — no bespoke judge framework needed. |
| **Confidence** | 85% |
| **Next step** | `/writing-plans` — draft `PLAN.md` for the foundation-first scope (adapter → metrics → dataset → runner → baseline). One dependency-resolution spike must run first (see Risks). |

---

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | Monorepo (pnpm + Turborepo). BE = `apps/api/` (FastAPI); FE = `apps/web/` (Next.js). Single Python venv at repo root `.venv`. |
| Primary language + runtime | Python 3.10+ (Docker runs 3.12, local up to 3.14) |
| Frameworks / platforms | FastAPI (`<0.137`), Starlette (`<1.3`), LangGraph `>=1.0,<2.0`, LangChain `>=1.0,<2.0`, Pydantic v2 (`>=2.6,<3`) |
| Relevant packages | `langchain-openai>=0.3`, `langchain-anthropic>=1.0`, `langchain-google-genai>=4.0`, `pytest>=9.0`, `langgraph-checkpoint-sqlite/postgres>=3.0`, `langfuse>=3.0` |
| Detectable versions | AI stack pinned in `apps/api/requirements-ai.txt`; core in `apps/api/requirements.txt`. `deepeval` **not present**. |
| Important constraints | (1) Must **NOT** force-upgrade fastapi/starlette/pydantic beyond caps — "stop and escalate rather than nudging those caps" (`requirements-ai.txt` header). (2) Tests/CI run with **no LLM key** → `FakeLLM` + `DeterministicFakeEmbedding` (no network). (3) BE work lives in `apps/api/` (CLAUDE.md). (4) Services raise domain exceptions, ORM confined to repositories — but eval is standalone tooling, mostly exempt. |

---

## Feature Understanding and Assumptions

- **Requested feature:** Offline evaluation harness for the Travel Assistant using DeepEval + G-Eval. Datasets (~15-20 cases) targeting known bugs/features (MIN-51 search-vs-booking intent, MIN-57 response language, MIN-46 tool args_schema, MIN-54 format), custom G-Eval rubrics per dimension, a CI-friendly runner, a recorded baseline. Grader = cheap Haiku-class model.
- **What success appears to mean:** `python -m eval.<runner>` (keyed) produces per-metric pass/fail scores + reasons over the dataset; a baseline is recorded; the existing no-network routing smoke still passes in CI without a key.
- **Assumptions from the request (confirmed at intake):** foundation-first scope (CI wiring + how-to doc deferred to a follow-up); keep the routing smoke and **layer** DeepEval alongside (not migrate); place under `apps/api/eval/`.
- **Assumptions still needing confirmation:** (a) grader model identity/provider for the baseline run — ticket suggests Haiku-class (`claude-haiku-4-5` per LangChain's own grader); (b) that `deepeval`'s transitive tree resolves **without** bumping the fastapi/starlette/pydantic caps (must be verified by a spike, see Risks).

---

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `apps/api/eval/` already exists: `run_eval.py` (routing-accuracy, no-network, FakeLLM-driven, `ROUTING_THRESHOLD=0.9`), `metrics.py` (`routing_accuracy()`), `datasets/routing.json` (5 cases). Not DeepEval. |
| `Local` | `app/clients/llm.py` exposes `get_llm()`, `get_fast_llm()`, `get_agent_llm(name)` via `init_chat_model()` — provider-agnostic (openai/anthropic/google_genai), key injected from settings, `streaming=True`, `max_retries=0`. `FakeLLM` for tests. |
| `Local` | Full agent turn: `graph.ainvoke({"messages":[HumanMessage(content=...)], "user_id":uid, "trip_id":...}, cfg, context=ctx)` → `result["messages"]` (final reply = last `AIMessage.content`), `result["current_flow"]` (intent), tool calls via `AIMessage.tool_calls` / `ToolMessage`. Needs a `thread_id` in `cfg` (checkpointer) + `AgentContext`. Source: `app/routers/agent.py:205-278`. |
| `Local` | `resolve_travel_graph(app)` / `build_graph(...)` (`app/agents/graph.py`) build the compiled graph; router resolves the shared one built once in lifespan. Tests swap a FakeLLM-backed graph via one override. |
| `Docs` | `GEval(name, criteria, evaluation_params=[SingleTurnParams.INPUT, ...], threshold, strict_mode, model=...)` — auto-derives eval steps from NL criteria; `model=` accepts a name string **or** a custom model object. Per-metric judge model supported. |
| `Docs` | `LLMTestCase(input, actual_output, expected_output?, context?, retrieval_context?, tools_called?, expected_tools?)` — only `input`+`actual_output` mandatory. `ToolCall(name=...)`. |
| `Docs` | `ToolCorrectnessMetric` needs `tools_called`+`expected_tools` — **deterministic, no judge LLM**. `AnswerRelevancyMetric(threshold, model, include_reason)` needs input+actual_output. `HallucinationMetric(threshold)` needs input+actual_output+**context** (ground-truth docs). |
| `Docs` | Custom judge = subclass `DeepEvalBaseLLM` implementing `load_model / generate(prompt)->str / a_generate / get_model_name`, wrapping a LangChain model (`.invoke(prompt).content`). DeepEval evaluates **locally by default**; Confident AI cloud is opt-in (`deepeval login`). Runner options: `evaluate(test_cases, metrics)` or pytest `assert_test(golden, metrics)` + `@pytest.mark.parametrize`. Install: `pip install -U deepeval`. |
| `Upstream` | LangChain `RubricMiddleware` (deepagents) — grader sub-agent (`model`, `system_prompt`, `tools`, `max_iterations`) reviews transcript, returns `satisfied / needs_revision / …`; on `needs_revision` injects feedback as HumanMessage and re-loops. Activates only when a rubric is passed at invoke. **deepagents-specific** — travel-pi uses raw LangGraph, so this is Phase-2/MIN-59 reference only. |
| `Inference` | DeepEval custom models must return valid JSON for schema-enforcing metrics (GEval/AnswerRelevancy). A bare `.content` string adapter can fail JSON parsing → the adapter should use `.with_structured_output(schema)` when DeepEval passes a `schema` arg. (Flagged as a risk; not yet reproduced.) |

---

## Local Findings

- **Relevant files:** `apps/api/eval/{run_eval.py,metrics.py,__init__.py}`, `apps/api/eval/datasets/routing.json`; `app/clients/llm.py`; `app/agents/{graph.py,supervisor.py,context.py,state.py,constants.py}`; `app/routers/agent.py`; `app/core/llm_providers.py`, `app/core/config.py` (settings: `llm_provider`, `llm_model`, `fast_llm_model`, per-provider `api_key_field`); `docs/solutions/agent/reflection-humanmessage-language-flip*.md` (directly relevant to the MIN-57 response-language criterion).
- **Existing abstractions / extension points:** `get_llm()`/`get_fast_llm()` (grader model source); the compiled graph + `graph.ainvoke(...)` (agent-under-test driver); `AgentContext`/`resolve_agent_context` (tier + reflection flags); `FakeLLM` (no-network smoke path). The current `run_eval.py` already models the "inject deps so CI drives FakeLLM; `main()` uses the real LLM" split — **reuse this exact pattern** for the DeepEval layer.
- **Conventions worth preserving:** no-network default in CI (routing smoke stays FakeLLM); provider-agnostic (never import a provider SDK directly — go through `get_llm`/`init_chat_model`); eval lives in `apps/api/eval/`.
- **What can be reused:** the provider client, the graph driver, the deps-injection runner pattern, `datasets/` layout, threshold-gating idea.
- **What is missing locally:** DeepEval itself; a `DeepEvalBaseLLM` grader adapter; G-Eval criteria definitions; a graph→`LLMTestCase` builder (extract final reply + `tools_called` + `current_flow`); per-sub-agent datasets; a keyed DeepEval runner + baseline record.

---

## Upstream Findings

- **Repositories inspected:** `langchain-ai/deepagents` (RubricMiddleware), `confident-ai/deepeval` (via docs).
- **Pattern present upstream:** DeepEval's LangChain-agent test pattern uses `EvaluationDataset(goldens=[Golden(input=...)])` + `@pytest.mark.parametrize("golden", ...)` + `assert_test`, and an optional `deepeval.integrations.langchain.CallbackHandler` for tracing. Travel-pi should drive its **own compiled graph** (not `create_agent`) and build `LLMTestCase` manually from `result` — the CallbackHandler/TaskCompletionMetric path assumes DeepEval owns agent creation, which we don't want.
- **How closely it matches:** metric API matches perfectly; the agent-driving glue must be custom (our graph has supervisor + sub-agents + checkpointer + context).
- **Upstream gaps:** RubricMiddleware is a `deepagents` construct; not portable to raw LangGraph without adopting deepagents. Correctly deferred to **MIN-59**.

---

## Docs Findings

- **Official sources checked:** DeepEval docs via Context7 `/confident-ai/deepeval` (High reputation, 7329 snippets): GEval, tool-correctness, hallucination, custom-LLM guide, getting-started, FAQ. LangChain deepagents rubric blog/reference.
- **Version status:** DeepEval is version-agnostic in the ticket; **must pin** a `deepeval>=X,<Y` in `requirements-ai.txt` after the resolution spike confirms caps hold. LangChain/LangGraph are version-matched (1.x, confirmed from manifest).
- **Built-in capabilities that already support the feature:** `GEval` (custom NL rubric = the ticket's core ask), `ToolCorrectnessMetric` (MIN-46 args/tool correctness, deterministic), `AnswerRelevancyMetric`, `HallucinationMetric` (needs a `context` ground-truth per case). Per-metric `model=` selection lets the grader be Haiku-class while heavier metrics could differ.
- **Current recommended APIs:** `evaluate(test_cases, metrics)` for batch/report; `assert_test` for pytest gating; `DeepEvalBaseLLM` for custom judges. Local-first (no cloud login required).
- **Caveats / migration notes:** (1) Custom judge JSON-schema gotcha (see Risks). (2) DeepEval pulls its own transitive tree — resolution against the fastapi/starlette/pydantic caps is the top risk. (3) Response-language checking (MIN-57) as a GEval criterion needs the judge to reliably detect language — write the criterion explicitly ("actual_output must be in the same language as input").

---

## Recommendation

- **Primary recommendation:** **Adapt upstream + thin adapter.** Add `deepeval` (eval-only) → build `eval/grader.py` (`DeepEvalBaseLLM` wrapping `get_llm(model=<haiku>)`) → `eval/metrics_geval.py` (GEval criteria + built-in metrics with thresholds) → `eval/harness.py` (graph→`LLMTestCase` builder: drive `graph.ainvoke`, extract final reply / `tools_called` / `current_flow`, fresh `thread_id` per case) → `eval/datasets/*.json` per sub-agent → `eval/run_deepeval.py` (keyed runner + baseline). Keep `run_eval.py` routing smoke untouched as the free no-network CI gate.
- **Why lightest credible path:** every criterion maps to an existing DeepEval metric; the judge maps 1:1 onto the existing provider client; no new judge framework, no change to production agent code.
- **Why the next-best alternative lost:** *hand-rolled LLM-as-judge* (no dep) was rejected — it re-implements GEval/ToolCorrectness/Hallucination scoring, report generation, and pytest integration that DeepEval already ships, for no benefit. *Migrating routing eval into DeepEval* was rejected at intake — loses the free no-network smoke.
- **What would change this:** if the dependency spike shows `deepeval` forces fastapi/starlette/pydantic past their caps, escalate (per `requirements-ai.txt` rule) — options then are a separate eval venv/extra, or pinning an older deepeval.

---

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:**
  1. **Dependency resolution (Deep, top risk).** `pip install deepeval` into `.venv` may bump fastapi/starlette/pydantic beyond `requirements.txt` caps. Mitigation: install-spike **first**; if caps break → stop & escalate (do not nudge caps). Consider an isolated eval extra.
  2. **Custom-judge JSON schema.** GEval/AnswerRelevancy expect structured JSON from the judge; a `.content`-string adapter can fail parsing. Mitigation: implement the adapter's `generate/a_generate` to honor DeepEval's `schema` arg via `.with_structured_output(schema)`.
  3. **Cost/latency & flakiness of LLM-judge runs.** Baseline run hits a real provider (spend + non-determinism). Mitigation: keep DeepEval runs **keyed/manual + gated** (not in the no-key CI path); this is *why* CI wiring was deferred (foundation-first).
  4. **Checkpointer state bleed.** Each case must use a fresh `thread_id` or conversation history leaks across cases. Mitigation: mint a unique `thread_id` per test case.
  5. **`HallucinationMetric` needs `context`.** Requires a ground-truth doc per case — only feasible for cases where expected hotel/flight facts are known. Mitigation: apply it selectively, not to every case.
- **Evidence gaps:** exact `deepeval` version that resolves cleanly (spike pending); whether the language-detection GEval criterion is reliable enough on Haiku-class (empirical, resolved at baseline).
- **Version uncertainties:** `deepeval` pin (TBD post-spike).
- **Follow-up questions for the user (max 2):**
  1. Grader model for the baseline: OK to use `claude-haiku-4-5` via the `anthropic` provider (needs `ANTHROPIC_API_KEY` locally), or a different provider/model?
  2. For the baseline "mốc so sánh" — record against **current (pre-fix)** agent behavior as the ticket implies, correct?

---

## Source Pack

- **Local files read:** `apps/api/eval/{__init__.py,metrics.py,run_eval.py}`, `apps/api/eval/datasets/routing.json`, `apps/api/requirements.txt`, `apps/api/requirements-ai.txt`, `apps/api/app/clients/llm.py`, `apps/api/app/routers/agent.py`, `apps/api/app/agents/graph.py` (grep), CLAUDE.md, `.github/workflows/ci.yml` (listing).
- **Upstream/pages checked:** `langchain.com/blog/introducing-rubrics-for-deepagents`, `reference.langchain.com/python/deepagents/middleware/rubric`, `github.com/langchain-ai/deepagents`.
- **Official docs:** Context7 `/confident-ai/deepeval` — GEval, metrics-tool-correctness, metrics-hallucination, guides-using-custom-llms, getting-started, faq, evaluation-test-cases, what-is-an-eval-harness.

---

## Evidence Boundary

> **Confirmed from artifacts:** existing routing eval + its no-network pattern; the provider-agnostic LLM client API; the full agent-turn invocation + result shape (messages/current_flow/tool_calls); DeepEval metric APIs, `LLMTestCase`/`ToolCall` shapes, `DeepEvalBaseLLM` extension, local-first execution; RubricMiddleware is deepagents-only.
> **Inferred from patterns:** the custom-judge JSON-schema gotcha (documented pattern, not yet reproduced here); that reusing `run_eval.py`'s deps-injection split is the cleanest runner shape.
> **Not checked:** actual `pip install deepeval` resolution against the repo caps (the pending spike); the exact contents of `app/agents/context.py`/`state.py` field names for `AgentContext`/`current_flow` (confirmed present via router usage, not field-by-field); whether `ci.yml` currently runs the routing smoke (file not read in full).
