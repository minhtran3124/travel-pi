# LangGraph Runtime Config — Research & Best Practices

> Status: research / advisory · Created: 2026-06-27 · Scope: `apps/api/app/agents`, `tools`, `routers/agent.py`
> Source of truth for docs: LangGraph 1.0 official docs (Context7 `/websites/langchain_oss_python_langgraph`).

## TL;DR

**Q: Do we support RunnableConfig with LangGraph today?**
**Partially.** We already *pass* a config dict on every invoke (`configurable.thread_id`,
`recursion_limit`, `callbacks`, `metadata`) — that is a `RunnableConfig` in practice and is
correctly powering the checkpointer + Langfuse tracing. But:

- We never type it as `RunnableConfig`.
- No node or tool **reads** `config["configurable"]`.
- App-level per-request data (`user_id`, `trip_id`) is threaded through **graph state**, and
  model selection is fixed at build time.

On **LangGraph 1.0** (which we pin: `langgraph>=1.0,<2.0`), the recommended way to inject
per-request, non-persisted context is the **new `Runtime` / `context_schema` API** — *not*
`config["configurable"]`, and *not* state. We are not using it yet. This doc explains the
distinction and what (if anything) to adopt.

---

## 1. What we do today

| Concern | Mechanism | Reference |
|---|---|---|
| Graph build | `StateGraph(TravelAgentState).compile(checkpointer, store)`, built once at startup | `app/agents/graph.py:40`, `app/core/lifespan.py:59` |
| Invoke | `graph.ainvoke(state_dict, cfg)` — `cfg` passed positionally | `app/routers/agent.py:109` |
| `cfg` contents | `{"configurable": {"thread_id": ...}, "recursion_limit": ..., "callbacks": ..., "metadata": ...}` | `app/routers/agent.py:82` |
| Per-request user data | `user_id`, `trip_id` placed in the **initial state dict** | `app/routers/agent.py:115` |
| Trip context | DB-loaded inside `load_context_node`, stored in `state["trip_context"]` | `app/agents/nodes.py:31` |
| Tool injection | `InjectedState("user_id")`, `InjectedStore` (no config read) | `app/tools/memory_tools.py:22` |
| Model selection | Fixed per-node at build time via `get_agent_llm(agent_name)` | `app/clients/llm.py` |
| Versions | `langgraph>=1.0,<2.0`, `langchain>=1.0,<2.0` | `apps/api/requirements-ai.txt` |

Node signatures are uniformly `def node(state) -> dict` — none accept `config` or `runtime`.

---

## 2. The three channels in LangGraph 1.0 (the mental model)

LangGraph separates *what flows through a run* into three distinct channels. Picking the
right one is the whole game:

| Channel | Mutable? | Persisted in checkpoint? | Visible to LLM? | Use for |
|---|---|---|---|---|
| **State** | yes (reducers) | **yes** | only fields you expose | conversation messages, accumulating results, anything the agent reads *and writes* across steps |
| **Context** (`Runtime`) | no (read-only per run) | **no** | no | per-request inputs that are constant for the run: `user_id`, `org_id`, model choice, feature flags, request-scoped deps |
| **Config** (`RunnableConfig`) | no | n/a (framework plumbing) | no | `thread_id`, `callbacks`, `metadata`, `recursion_limit`, `tags` — the runtime's own machinery |

Key consequence: **`user_id` / `trip_id` are arguably context, not state.** They are constant
for the run and never mutated by the agent — putting them in state means they get written into
every checkpoint snapshot for no benefit. (This is a *cleanliness* point, not a bug — our
current approach works.)

---

## 3. LangGraph 1.0 API: `Runtime` + `context_schema`

This is the v1.0 replacement for the old `config_schema` + `config["configurable"]` pattern.

### Node reads context via an injected `Runtime`

```python
from dataclasses import dataclass
from langgraph.graph import StateGraph, MessagesState
from langgraph.runtime import Runtime

@dataclass
class Context:
    user_id: str
    trip_id: str | None = None
    model_provider: str = "openai"

def call_model(state: MessagesState, runtime: Runtime[Context]):
    model = MODELS[runtime.context.model_provider]      # per-run model selection
    user_id = runtime.context.user_id                   # per-run identity
    thread_id = runtime.execution_info.thread_id        # framework value, not context
    ...

builder = StateGraph(MessagesState, context_schema=Context)   # <-- declares context
graph = builder.compile()

# Invoke: context is a FIRST-CLASS kwarg, separate from config
graph.invoke(
    {"messages": [...]},
    context=Context(user_id="u_123", trip_id="t_9", model_provider="anthropic"),
    config={"configurable": {"thread_id": "conv_42"}},   # config still carries thread_id
)
```

`Runtime` also exposes `runtime.store` and `runtime.execution_info` (incl. `thread_id`), so a
node no longer needs `InjectedStore`-style plumbing to reach the store.

### Tools read context + state via `ToolRuntime`

```python
from langchain.tools import ToolRuntime, tool

@tool
def get_user_info(runtime: ToolRuntime[Context, State]) -> str:
    """Look up user information."""
    user_id = runtime.state["user_id"]          # graph state
    org_id  = runtime.context.organization_id   # per-run context, not in state
    return f"User {user_id} in org {org_id}"
```

This is the 1.0 successor to our `InjectedState` / `InjectedStore` annotations. Our current
annotations still work; `ToolRuntime` is the unified, typed alternative.

### `RunnableConfig` is **not** deprecated

`config` remains the channel for `thread_id`, `callbacks`, `metadata`, `recursion_limit`. In
the functional API you can still inject it directly:

```python
from langchain_core.runnables import RunnableConfig
from langgraph.func import entrypoint

@entrypoint(checkpointer=..., store=...)
def workflow(some_input, *, store, writer, config: RunnableConfig): ...
```

So our existing `cfg` dict is correct and stays. The 1.0 change is **additive**: move
*application context* out of `config["configurable"]` into `context=`, and leave *framework
plumbing* in `config`.

---

## 4. Best practices (LangGraph 1.0)

1. **Three-channel discipline.** State = mutable + persisted. Context = read-only per-run,
   not persisted. Config = framework plumbing (`thread_id`, `callbacks`, `metadata`,
   `recursion_limit`). Never overload one for another's job.
2. **App context goes in `context=`, not `config["configurable"]`.** `configurable` is now for
   the runtime's own keys; user/request data belongs in a typed `context_schema`.
3. **Type the context schema** (dataclass or `TypedDict`) so nodes/tools get IDE + runtime
   safety on `runtime.context.*`.
4. **Don't persist constants in state.** Identity/flags that never change during a run are
   context, keeping checkpoints lean and snapshots meaningful.
5. **Runtime model selection via context**, not build-time, *if* you need per-request model
   choice (we currently fix it per node — fine until a request needs to override).
6. **Keep `config` for tracing/threading.** `thread_id`, Langfuse `callbacks`, `metadata`,
   `recursion_limit` stay exactly where they are — that part is already correct.
7. **Prefer `Runtime`/`ToolRuntime` over `Injected*`** for new code — unified, typed access to
   state + context + store.

---

## 5. Gap analysis & recommendation

| Best practice | Status | Action |
|---|---|---|
| Pass `config` with `thread_id`/callbacks/metadata | ✅ Done | none |
| Typed `RunnableConfig` | ⚪ Cosmetic | optional: annotate `cfg` |
| App context in `context=` w/ `context_schema` | ❌ Not adopted | candidate refactor (see below) |
| `user_id`/`trip_id` out of persisted state | ❌ In state | move to context |
| `Runtime` / `ToolRuntime` over `Injected*` | ❌ Using `Injected*` | adopt incrementally for new tools |
| Per-request model selection | ❌ Build-time only | adopt only if a real need appears |

**Recommendation — do this only if there's a driver, not for its own sake.** Our current
state-threading + `Injected*` approach is functional and idiomatic for LangGraph ≤0.x. The
1.0 `Runtime`/`context` API is the cleaner long-term path, but a migration touches every node
signature and the state schema (Rule 4 territory — state shape change). Suggested sequencing:

- **Now (low cost):** type the router `cfg` as `RunnableConfig`; document the three-channel
  model in `WORKFLOW.md`. No behavior change.
- **When a feature needs it** (e.g. per-request model override, request-scoped deps, or
  trimming checkpoint bloat): introduce a `context_schema` dataclass, move `user_id`/`trip_id`
  into `context=`, and migrate nodes to `runtime: Runtime[Context]` / tools to `ToolRuntime`.
- **Don't** big-bang refactor purely for style — it's a wide blast radius across `agents/` and
  `tools/` with no user-visible win until one of the above drivers lands.

---

## 6. References

- Use the graph API — runtime context: https://docs.langchain.com/oss/python/langgraph/use-graph-api
- Graph API (nodes, `Runtime`, `execution_info`): https://docs.langchain.com/oss/python/langgraph/graph-api
- Workflows & agents (`ToolRuntime`): https://docs.langchain.com/oss/python/langgraph/workflows-agents
- Functional API (`RunnableConfig` injection): https://docs.langchain.com/oss/python/langgraph/functional-api
