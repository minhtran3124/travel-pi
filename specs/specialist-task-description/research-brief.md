# specialist-task-description — Research Brief

Depth: **Standard** (intake lane `normal` → Standard per `rules/research-depth.md`; re-checked
with evidence below — no Deep signal surfaced, no upgrade). Waiver: none requested.
External surface: **none** — no dependency added or upgraded, no external system, no
version-specific API beyond what `_base.py` already uses (`SystemMessage`, `Send`).

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **Adapt upstream** — take deepagents' fork-mode shape (fixed preamble + task description appended after the inherited history) but deliver it as a trailing `SystemMessage`, not the `HumanMessage` deepagents uses. |
| **Why this is the lightest credible path** | Every needed hook already exists: `AgentTask.query` is written per task and read by nothing; `_base.py` already assembles `[system_msg, *messages]` in one place for all 5 specialists; the fan-out worker already carries `task` into the inner state. The change is a supervisor field + one append in `_base.py` + a prompt version. |
| **Confidence** | 80% |
| **Next step** | `writing-plans`: decide fork 1 (schema shape) as "parallel `task_queries` list, `plan` untouched" and fork 2 as "both paths", then plan the v13 prompt, the `_base.py` append, tests, and 2 fan-out goldens. |

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | pnpm/Turbo monorepo; this change is BE-only (`apps/api`) |
| Primary language + runtime | Python 3.14 locally (`.venv`), 3.12 in Docker |
| Frameworks / platforms | FastAPI; LangGraph hand-rolled supervisor + ReAct subgraphs |
| Relevant packages | langgraph 1.2.6, langgraph-prebuilt 1.1.0, langchain-core 1.4.8, langchain-openai 0.3.34, pydantic 2.13.4 (from `pip list` in `.venv`) |
| Detectable versions | above; `requirements.txt` carries no langgraph/langchain pins by that name (grep returned nothing) — versions come from `requirements-ai.txt`/lock, not re-checked |
| Important constraints | prompts are registry-versioned: new `supervisor/v13.md` + bump `active.yaml` (never edit v12 in place — `docs/solutions/agent/supervisor-active-yaml-is-a-pointer.md`); a running dev agent needs a graph rebuild to see it; internal steering text must be `SystemMessage` (`docs/solutions/agent/reflection-humanmessage-language-flip.md`); `hooks/risk-corroboration.sh` maps the token `role` to the `authorization` block gate |

## Feature Understanding and Assumptions

- **Requested feature:** step 2 of the *Fork hay Isolated* review — the supervisor emits a per-task `query` (not the full user sentence copied N times) and `_base.py` appends that task text to the specialist's input behind a fixed preamble, delivered as a `SystemMessage`.
- **What success appears to mean:** on a fan-out turn each worker receives its own slice ("find flights to Tokyo" vs "what visa do I need") instead of guessing its share from the whole message; offline tests pin that the note reaches the model input; a fan-out golden with `tasks_expected` + a judged rubric shows no regression and, ideally, the synthesized answer covers both slices.
- **Assumptions from the request:** no framework swap (MIN-61 spike closed that); reflection changes (step 3) are out of scope; caching (step 1) is a separate spec already planned.
- **Assumptions still needing confirmation:** (1) the schema shape for the per-task query — default is a field parallel to `plan`, keeping `plan` a bare-name list; (2) the note is appended on the single-intent path too, not only on fan-out. Either being wrong changes the plan's task list, not the recommendation.

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `app/agents/supervisor.py:365-378`: `last_user_message` is the `query` of every `AgentTask`; the comment says "each worker prompt narrows the focus" — i.e. narrowing was delegated to the specialist prompt, which never sees the task. |
| `Local` | `grep -rn '\.get("query")\|\["query"\]\|task\.query' apps/api/app/agents` → 0 hits: no consumer of `AgentTask.query`. |
| `Local` | `app/agents/subagents/_base.py` `assistant()`: `system_msg = with_reply_language(system_with_summary(state, ground_current_date(system, tz)), state)`; `bound.invoke([system_msg, *state["messages"]])`. One assembly point for all five specialists. |
| `Local` | `app/agents/subagents/synthesis_worker.py`: `inner_state["task"] = task` is set before `subagent.ainvoke(inner_state, …)`, but `TravelAgentState` declares no `task` key (`grep "task:" app/agents/state.py` → none) and a compiled subgraph **drops** undeclared input keys — probed 2026-09-10 with a one-node `StateGraph(TravelAgentState)`: `task` arrived as `None`, `tasks` intact. So the inner `assistant` cannot read `task`; the worker must pass `tasks=[task]`. |
| `Local` | `app/agents/supervisor.py:65-150`: `SupervisorIntent.plan` is `list[Literal[...]] | None` with a `mode="before"` coercer (gh-180) and `tests/agents/test_supervisor_plan_semantics.py::test_wire_schema_keeps_plan_enum` pins the wire schema — turning `plan` entries into objects breaks that test and re-opens the gh-180 surface. |
| `Local` | Supervisor is invoked via `llm.with_structured_output(SupervisorIntent, method="function_calling")` (`supervisor.py:266`); 8 tests construct `SupervisorIntent(target_agent=…, plan=[…])` directly, so a new field must default to `None`. |
| `Local` | `route_tasks` (`nodes.py:306-337`) already ships `{**state, "task": t}` per `Send`; nothing to add there. |
| `Local` | Eval: `eval/adapters/langgraph_runner.py:251` records `Trace.meta["tasks"] = [t.agent …]` and `tasks_expected` compares agent sets only — it cannot see `query`. Fan-out goldens exist (`routing-multi-en-03`, `-04`); a per-slice quality claim needs a judged rubric on the answer, not `tasks_expected`. |
| `Local` | `docs/solutions/agent/reflection-humanmessage-language-flip.md` (critical): a synthetic `HumanMessage` flipped reply language; fix = `SystemMessage`. Directly applies to the task note. |
| `Upstream` | deepagents `middleware/subagents.py` `_fork_messages()`: pops a trailing `AIMessage` with `tool_calls`, then `return [*effective, HumanMessage(content=_FORK_TASK_PREAMBLE + description)]`. The preamble tells the model it *is* the invoked subagent, must not delegate, and must reuse facts already in the history. |
| `Upstream` | Blog: fork = worker/memorizer (inherit history), isolated = verifier/researcher (empty context). Our fan-out workers are researchers by role but forked by mechanism — the artifact already accepted that trade-off (cache hit is 71.9%). |
| `Inference` | Our supervisor never appends its structured decision to `messages` (its `Command.update` has no `messages` key), so the "pop trailing tool call" step has nothing to pop — the fork is clean already. |
| `Inference` | The single-intent query will usually restate the user sentence; the note there is cheap (cache prefix unchanged — it is appended *after* the history, so it only affects the uncached tail) and gives step 3 (reflection) the same text to reuse. |

## Local Findings

- **Relevant files:** `app/agents/supervisor.py`, `app/agents/schemas.py` (`AgentTask`), `app/agents/subagents/_base.py`, `app/agents/subagents/synthesis_worker.py`, `app/agents/nodes.py` (`route_tasks`), `app/agents/state.py` (helpers), `app/prompts/supervisor/v12.md` + `active.yaml` + `CHANGELOG.md`, tests `tests/agents/test_supervisor_plan_semantics.py`, `test_multi_intent_routing.py`, `test_supervisor.py`, eval `eval/datasets/routing.json`.
- **Existing abstractions / extension points:** `AgentTask.query` (already the right shape, just unfilled); `_base.py::assistant` (single input-assembly point); `state.py` helper style (`with_reply_language` returns a new `SystemMessage` — a sibling `with_task_note(state)` fits the convention); registry-versioned prompts.
- **Conventions worth preserving:** one leading `SystemMessage` for provider compatibility (`system_with_summary` docstring); internal steering as `SystemMessage`; `plan` stays a bare-name enum on the wire; new prompt = new version file + `active.yaml` bump + CHANGELOG entry.
- **What can likely be reused:** everything above; no new module.
- **What appears missing locally:** a supervisor output field for per-task queries; a reader of `task`/`tasks[].query` in `_base.py`; a fan-out golden whose metric can see the answer quality per slice; a test that the note is a `SystemMessage` and is absent from the persisted `messages` (it must be built at invoke time, not appended to state, or it would be replayed every later turn like the SSE tool events were in PR #140).

## Upstream Findings

- **Repositories inspected:** `langchain-ai/deepagents` (`libs/deepagents/deepagents/middleware/subagents.py`, pinned commit 15454a8 in the blog link; fetched `main`).
- **Pattern present upstream:** fork mode = inherited history + trailing tool-call excision + `HumanMessage(preamble + task)`.
- **Worth modeling:** the preamble content (you are the invoked subagent; do not delegate; reuse facts already established above; "your actual task is below").
- **Match to this repo:** mechanism matches (`_base.py` already forks); role differs (`HumanMessage` there, `SystemMessage` here by recorded bug); excision step not needed here.
- **Gaps:** deepagents is middleware over `create_agent`; MIN-61 already found it cannot wrap our hand-rolled subgraphs, so only the *shape* is adopted.

## Docs Findings

- none (local-only; no external surface). `SystemMessage` mid/trailing placement is already exercised by `REFLECTION_REVISE_NOTE` in `nodes.py` on the same providers.

## Recommendation

- **Primary:** adapt upstream. (a) `SupervisorIntent` gains `task_queries: list[str] | None` (or `primary_query: str | None` + per-plan-step queries), positionally aligned with `[target] + plan`, defaulted `None`; supervisor falls back to `last_user_message` for any missing entry so a lazy model degrades to today's behaviour. (b) `_base.py::assistant` builds a trailing `SystemMessage` = fixed preamble + the task text, sourced from `state.get("task")` (fan-out) or `state["tasks"][0]` (single path), and passes `[system_msg, *messages, task_note]` to the model without writing the note to state. (c) `supervisor/v13.md` teaches the per-task query (one clause per specialist, in the traveller's language, no invented details) — the `# Role:` heading can stay: `risk-corroboration.sh` scans code only (`:!*.md`), so only the new `Field(description=...)` in `supervisor.py` must avoid the word. (d) Tests: schema default keeps 8 existing constructors green; wire-schema test extended; a FakeLLM test asserts the note reaches the model input as `SystemMessage` and never lands in the checkpoint. (e) Eval: add 2 fan-out goldens (vi + en) with a judged rubric on slice coverage; keep `tasks_expected`.
- **Why lightest:** no new node, no state schema change (task note is ephemeral), no prompt for specialists changes, `plan` wire schema unchanged.
- **Why the next-best lost:** turning `plan` into `[{agent, query}]` objects is the "natural" shape but breaks `test_wire_schema_keeps_plan_enum`, re-enters the gh-180 coercer, and changes the enum the model has been reliable with since v9. `HumanMessage` delivery (upstream-literal) lost to the recorded language-flip bug.
- **What would change this:** if the model reliably fills per-step queries only when they are nested with the agent name, the object shape wins and the coercer must grow; a judged A/B on the 2 new goldens decides.

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:** (1) a trailing `SystemMessage` after tool messages on the OpenAI path — already proven safe by `REFLECTION_REVISE_NOTE`; (2) the note text leaking into `messages` via a careless `return {"messages": [...]}` — pinned by test; (3) revision loop: reflection's REVISE re-enters the specialist, which will rebuild the note — fine, but the note must be idempotent (built, not appended); (4) supervisor prompt regression on `plan` decisions (gh-149/#173 area) — routing goldens k=3 before/after.
- **Evidence gaps:** value is only measurable with the paid judged eval (`make eval-check`); offline suite proves plumbing only. `tasks_expected` cannot see query text.
- **Version uncertainties:** none material.
- **Follow-up questions for the user:** (1) Apply the note on the single-intent path too (default yes)? (2) Accept the parallel-list schema over `plan`-as-objects (default yes)?

## Source Pack

- **Local files read:** `apps/api/app/agents/supervisor.py`, `schemas.py`, `state.py`, `nodes.py`, `subagents/_base.py`, `subagents/synthesis_worker.py`, `app/prompts/supervisor/v12.md`, `app/prompts/active.yaml`, `app/prompts/CHANGELOG.md`, `tests/agents/test_multi_intent_routing.py`, `tests/agents/test_supervisor_plan_semantics.py` (names), `eval/datasets/routing.json`, `eval/adapters/langgraph_runner.py:251`, `eval/README.md:245-254`, `docs/solutions/agent/reflection-humanmessage-language-flip.md`, `specs/specialist-task-description/SUMMARY.md`, artifact *Fork hay Isolated*.
- **Upstream repositories or pages checked:** https://www.langchain.com/blog/organizing-context-in-a-multi-agent-harness ; https://raw.githubusercontent.com/langchain-ai/deepagents/main/libs/deepagents/deepagents/middleware/subagents.py
- **Official docs domains or pages checked:** - none (local-only; no external surface)

## Evidence Boundary

> Confirmed from artifacts: no reader of `AgentTask.query`; `_base.py` single assembly point; `Send` payload carries `task`; wire-schema test on `plan`; deepagents preamble + `HumanMessage`; installed package versions.
> Inferred from patterns: trailing `SystemMessage` is provider-safe (by analogy with `REFLECTION_REVISE_NOTE`); single-intent note is cache-neutral (appended after history).
> Not checked: `requirements-ai.txt` pins; whether `gpt-5-mini` fills a parallel `task_queries` list reliably (needs the judged run); Anthropic path behaviour with a trailing system message (not the configured provider today).
