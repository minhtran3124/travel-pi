---
slug: agent-fault-tolerance
status: proposed
owner: Minh Tran
created: 2026-07-03
linear: MIN-49
---

# Agent Fault-Tolerance — RetryPolicy + graceful degradation

## 1. Motivation

The agent graph (`app/agents/`) uses **none** of LangGraph's fault-tolerance
primitives. LangGraph (installed **1.2.6**, pinned `>=1.0,<2.0` in
`apps/api/requirements-ai.txt`) already exposes `retry_policy`, `error_handler`,
and `timeout` on `StateGraph.add_node()` — verified against the installed source.
Two real failure surfaces are currently unprotected:

- **LLM provider calls** (rate-limit / network blips) in every sub-agent
  `assistant` node and the top-level LLM nodes — a single 429 or connection reset
  500s the whole `/agent/stream` request.
- **Real external I/O** in the `weather_service` / `routing_service` tools
  (the only real network per `CLAUDE.md`) — a transient Open-Meteo / ORS timeout
  is caught and reported to the user as "unavailable" with **no retry**.

### Key finding — today's error handling actively blocks retry

`app/agents/subagents/_base.py:43-61` (`_tool_error_to_message`) is the shared
`handle_tool_errors` handler for **every** sub-agent's `tools` node. It catches
*every* exception (annotated `exc: Exception`) → `ToolMessage`, and the message
text tells the model **not to retry**. Combined with the tools themselves
wrapping all `AppError` (transient **and** logic) into `ToolException`
(`weather_tools.py:85/105/137`, `routing_tools.py:77/98`, `hotel_tools.py`), the
original exception type is lost and **no exception ever propagates** for a
`RetryPolicy` to catch. The error-classification must change *before*
`RetryPolicy` can fire.

## 2. Non-goals

- **No SAGA / booking compensation** (ticket item 3 dropped). `book_hotel` is the
  only booking tool bound to the agent — `book_flight` is **not** an agent tool
  (`FLIGHT_TOOLS = [search_flights]`). `book_hotel` calls the deterministic fake
  `BookingService`: a single atomic write in `session_scope()` raising **only**
  logic errors (`NotFoundError`/`ConflictError`), never transient, never partial.
  A retry could never fire and there is no partial write to compensate. Booking is
  **excluded from retry** — retry-exclusion *is* the safety mechanism.
  `BookingService.cancel()` (soft status transition) exists if a real provider is
  added later.
- **No TimeoutPolicy** (deferred to a follow-up). LangGraph timeouts work only on
  **async** nodes ("sync nodes cannot be safely cancelled in-process" — 1.0.8
  docs); the `assistant` and top-level LLM nodes are sync (`bound.invoke`).
  Applying `TimeoutPolicy` requires an async-node conversion out of scope here.
  Near-term timeout lever = the provider SDK request timeout (`init_chat_model`).
- **No change to deterministic fake services** (flights/hotels availability,
  trips, FX) — no real I/O, so retry/timeout does not apply.
- **No `set_node_defaults()`** — `assistant` and `tools` nodes need different
  policies (booking excluded), so explicit per-node config is clearer and avoids
  accidentally arming retry on the booking path.

## 3. Success criteria

1. A transient `UpstreamError` (`WeatherUnavailableError`/`RoutingUnavailableError`)
   from a weather/routing tool is **retried** by `RetryPolicy` (default 3 attempts).
2. After retries are exhausted, the user still gets a **graceful** "temporarily
   unavailable" `ToolMessage` — **no 500** on `/agent/stream` (no regression of
   today's UX).
3. A **logic** error (`NotFoundError`/bad args) is **not** retried — it converts to
   a `ToolMessage` immediately so the LLM self-corrects (as today).
4. LLM provider rate-limit / network errors on any LLM node are retried.
5. The booking path is unchanged and never auto-retried; all existing agent tests
   stay green.

## 4. Design

### 4.1 Error classification (the core)

Reuse the existing exception hierarchy (`app/exceptions.py`; `UpstreamError` and
its subclasses subclass `AppError`, so `except UpstreamError` must come **before**
`except AppError`):

| Class | Types | New behavior |
|---|---|---|
| **Transient** | `UpstreamError` + subclasses (`WeatherUnavailableError`/`RoutingUnavailableError`, 502) | Propagate **unwrapped** from the tool → `RetryPolicy` retries the `tools` node. On exhaustion, `error_handler` → graceful `ToolMessage`. |
| **Logic** | `NotFoundError`, `ConflictError`, `DomainValidationError`, `ValueError` | Wrap into `ToolException` → `handle_tool_errors` → `ToolMessage` (LLM self-corrects). |

**Two edits are both required — re-raising in the tool is necessary but NOT
sufficient.** The `handle_tool_errors` handler infers *which* exception types it
catches from its **first-parameter annotation** (LangGraph `ToolNode._infer_handled_types`).
Today `_tool_error_to_message(exc: Exception)` → catches **everything**, so even a
re-raised `UpstreamError` would be converted to a `ToolMessage` and `RetryPolicy`
would never fire.

> **Scope the narrowing to the retry sub-agents only (regression guard).** The
> narrowed handler is used **only** for concierge/planner (the `tools` nodes that
> get a `RetryPolicy` + `error_handler`). booking/budget/journal keep the existing
> catch-all `_tool_error_to_message(exc: Exception)` **unchanged** — narrowing them
> would let an unexpected non-`ToolException` error propagate out of a node with no
> retry and no `error_handler` → a **500 regression** vs today's graceful
> `ToolMessage`. A dedicated `_tool_error_logic_only(exc: ToolException)` handler is
> introduced for concierge/planner; the original handler is untouched.

For concierge/planner, the narrowed handler makes:

- `UpstreamError` (re-raised unwrapped by the tool) is **not** a `ToolException`
  → propagates out of the `tools` node → `RetryPolicy` sees it.
- Logic errors (wrapped into `ToolException` by the tool, incl. `ValueError`) are
  caught → `ToolMessage`.
- Any **unexpected** exception (a genuine bug, not `ToolException`) also propagates,
  but `TRANSIENT_RETRY.retry_on` only matches `UpstreamError`, so it is **not**
  retried — it falls straight through to the `error_handler` (graceful message).

> Note (`ValueError`): it is **not** an `AppError`, so today's `except AppError`
> clause never catches it — it currently escapes unwrapped. The weather/routing
> tools must therefore also wrap `ValueError` into `ToolException` (or the handler
> must catch it) for it to render as a self-correct `ToolMessage` rather than
> hitting the graceful fallback.

Flow at the `tools` node of **concierge** (weather) and **planner** (routing) —
the only two sub-agents with real-I/O tools:

```
tool → weather/routing_service
  ├─ UpstreamError (transient)  → NOT wrapped, propagates ──► RetryPolicy (retry_on=UpstreamError) retries
  │      └─ retries exhausted ──► error_handler → Command(goto="assistant",
  │                                 update={messages:[ToolMessage per pending tool_call_id]})
  ├─ NotFoundError/ValueError/… (logic) → wrapped ToolException ──► handle_tool_errors → ToolMessage
  └─ unexpected bug (not ToolException) → propagates ──► retry_on=False (no retry) ──► error_handler
```

### 4.2 Retry breadth (LLM calls)

`RetryPolicy` on **all** real LLM calls:

- Every sub-agent `assistant` node (`_base.py`) — always armed.
- Top-level LLM nodes in `graph.py`: `summarize`, `supervisor`, `reflection`,
  `extract_memory`. (`load_context`, `plan` make no LLM call → skipped.)

### 4.3 Component boundaries

- **`app/agents/retry.py` (new)** — single source of the policies:
  - `LLM_RETRY: RetryPolicy` — `retry_on = _is_retryable_llm`, a **provider-agnostic
    duck-typed predicate** (no `openai`/`anthropic` import — `clients/llm.py`
    forbids provider-SDK imports in the agent layer): retry when
    `getattr(exc, "status_code", None)` ∈ {408, 409, 429} or 500–599, **or**
    `isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, ConnectionError))`,
    **or** `exc.__class__.__name__ ∈ {"APIConnectionError","APITimeoutError","APIConnectionTimeoutError"}`.
    All other `RetryPolicy` fields keep the langgraph **defaults** (verified equal
    to the design's params: `initial_interval=0.5`, `backoff_factor=2`,
    `max_interval=128`, `max_attempts=3`, `jitter=True`).
  - `TRANSIENT_RETRY: RetryPolicy` — `retry_on = lambda e: isinstance(e, UpstreamError)`;
    **same** `max_attempts=3` / `initial_interval≈0.5s` / `backoff_factor=2` /
    `jitter=True` as `LLM_RETRY` (only `retry_on` differs).
  - `_tool_error_logic_only(exc: ToolException) -> str` — the **narrowed**
    `handle_tool_errors` handler for concierge/planner (annotation `ToolException`
    → only wrapped logic errors are caught; `UpstreamError` propagates). Lives here
    (not `_base.py`) to avoid a `retry.py ↔ _base.py` import cycle.
  - `ToolFaultPolicy` — a frozen dataclass `(retry_policy, handle_tool_errors,
    error_handler)`; `TOOL_FAULT = ToolFaultPolicy(TRANSIENT_RETRY,
    _tool_error_logic_only, graceful_fallback)` is the shared bundle concierge/planner import.
  - `graceful_fallback(state, error: NodeError) -> Command` — the tools-node
    `error_handler`. **Signature is `(state, error)` where the exception is a
    LangGraph `NodeError` (`from langgraph.errors import NodeError`), read via
    `error.error`** — NOT `(state, exc)`. It restores today's graceful degradation:
    the failing `tools` node produced **no** `ToolMessage` for any pending call, so
    it must emit **one `ToolMessage` per pending tool_call_id**, reconstructed from
    the last `AIMessage`'s `tool_calls` (`state["messages"][-1].tool_calls`),
    otherwise the next `assistant` invoke breaks (providers require exactly one
    response per tool call). Returns
    `Command(goto="assistant", update={"messages": [ToolMessage(content=GRACEFUL_MSG, tool_call_id=tc["id"]) for tc in ...]})`.
  - `GRACEFUL_MSG` — the exact text: today's `_tool_error_to_message` message
    **minus the "do not retry" clause** (the info is temporarily unavailable, tell
    the user to try again shortly).
- **`_base.py`** — `build_subagent(...)` gains **one** optional param
  `tool_fault: ToolFaultPolicy | None = None`, a small frozen dataclass bundling
  the three values that always travel together:
  `(retry_policy: RetryPolicy, handle_tool_errors: Callable, error_handler: Callable)`.
  - `assistant` node **always** gets `retry_policy=LLM_RETRY`.
  - `tools` node when `tool_fault is None` (booking/budget/journal): today's
    behavior exactly — `ToolNode(tools, handle_tool_errors=_tool_error_to_message)`,
    no `retry_policy`, no `error_handler`. **Unchanged.**
  - `tools` node when `tool_fault` is set (concierge/planner):
    `ToolNode(tools, handle_tool_errors=tool_fault.handle_tool_errors)` +
    `add_node("tools", …, retry_policy=tool_fault.retry_policy, error_handler=tool_fault.error_handler)`.
  - `_tool_error_to_message` is **left as-is** (catch-all, still the default). A new
    `_tool_error_logic_only(exc: ToolException)` (narrowed, no "do not retry"
    wording) is what the `ToolFaultPolicy` carries.
- **`concierge.py` / `planner.py`** — pass `tool_fault=TOOL_FAULT` (the shared
  `ToolFaultPolicy(TRANSIENT_RETRY, _tool_error_logic_only, graceful_fallback)`,
  exported from `app/agents/retry.py`). booking/budget/journal pass nothing.
- **`weather_tools.py` (3 sites) / `routing_tools.py` (2 sites)** — add
  `except UpstreamError: raise` **before** the `except AppError → ToolException`
  clause; wrap `ValueError` too (see §4.1 note) so only `UpstreamError` propagates.
- **`graph.py`** — add `retry_policy=LLM_RETRY` to the four top-level LLM nodes
  (`summarize`, `supervisor`, `reflection`, `extract_memory`).
- **`clients/llm.py` (`_build_chat_model`)** — pass `max_retries=0` to
  `init_chat_model(...)` so the **graph is the single retry owner** for LLM calls.
  Both providers otherwise retry internally (`langchain-openai` → OpenAI SDK
  default 2; `langchain-anthropic` default 2), which would stack under
  `LLM_RETRY` (~2×3 = 6 attempts). This is a shared-runtime-contract edit (Deep),
  authorized by the owner (decision **B**, 2026-07-03). `FakeLLM` ignores
  `max_retries`, so tests are unaffected.

### 4.4 Error handling & no-regression guarantee

The load-bearing risk is regressing today's graceful degradation. Re-raising
transient errors without a fallback would let an exhausted retry propagate out of
the graph and 500 `/agent/stream`. The `graceful_fallback` `error_handler` on the
concierge/planner `tools` nodes closes this: after `RetryPolicy` exhausts (or a
non-retryable exception surfaces), it emits a graceful `ToolMessage` and routes
back to `assistant`, preserving the current user experience.

**Multi tool-call correctness:** when the `assistant` emits several tool calls and
the `tools` node fails on one of them, the node returns **no** `ToolMessage` for
*any* of the pending calls. `graceful_fallback` must therefore emit a `ToolMessage`
for **every** `tool_call_id` in `state["messages"][-1].tool_calls`, not just one —
a provider rejects the follow-up `assistant` turn if any tool call lacks a
response. This is a hard correctness requirement, not a nicety.

## 5. Testing

- **Unit (tools):** weather/routing tool re-raises `UpstreamError` unwrapped, but
  still wraps `NotFoundError`/`CityNotFoundError`/`ValueError` into `ToolException`.
- **Unit (handler narrowing):** `_tool_error_to_message` catches `ToolException`
  (→ message) but lets `UpstreamError` propagate (asserts the annotation narrowing
  actually works via `ToolNode`).
- **Graph (tool retry fires):** inject a tool raising `WeatherUnavailableError`
  twice then succeeding (with `FakeLLM`) → assert the tool ran 3× (retried) and the
  run succeeds.
- **Graph (LLM retry fires):** inject an LLM (assistant node *and* a top-level node
  such as `supervisor`) raising a rate-limit/connection error on the first call →
  assert `LLM_RETRY` retries and the run succeeds. (Closes the asymmetry — LLM
  retry must be tested, not just tool retry.)
- **Graph (graceful exhaustion + multi-call):** tool raises `UpstreamError` on
  every attempt → assert the final state carries a graceful `ToolMessage` **for
  every pending `tool_call_id`** and the run does **not** raise / 500.
- **Regression:** logic error → immediate `ToolMessage` (self-correct); booking
  flow unchanged and never retried; full existing agent suite green.

## 6. Risks

- **Retry amplifies load / cost** on a sustained upstream outage — bounded by
  `max_attempts=3` + backoff + jitter; the graceful fallback caps user-visible
  latency at ~one backoff window.
- **`retry_on` mis-scoped for LLM** could retry a non-transient provider error
  (e.g. a 400 bad-request) — `LLM_RETRY.retry_on` must whitelist only
  rate-limit/connection classes, verified in xia2 against the actual provider SDK
  exception types raised through `init_chat_model`.
- **Async-execution assumption** — the graph already runs via `astream`; no node
  becomes async here, so behavior is unchanged apart from retry.

## 7. Open items for xia2 / planning

- ~~Exact provider-SDK exception classes for `LLM_RETRY.retry_on`~~ **RESOLVED**
  (xia2 + decision B): use the duck-typed `_is_retryable_llm` predicate (§4.3) — no
  SDK import — and set SDK `max_retries=0` in `clients/llm.py` so the graph is the
  single retry owner. Non-transient errors (e.g. 400) are excluded by the predicate.
- **`error_handler` mechanics** — signature confirmed as `(state, error: NodeError)`
  reading `error.error` (verified against installed LangGraph 1.2.6); confirm the
  exact `NodeError` import path and that returning `Command(goto=…, update=…)` from
  the tools node routes correctly. Confirm `ToolNode` annotation narrowing
  (`exc: ToolException`) lets `UpstreamError` propagate uncaught (verified in
  review; re-confirm during implementation on the installed version).
- Confirm `graph.py`'s top-level LLM nodes are the exact four listed (no other
  node makes a provider call). (Verified in review: `summarize`/`supervisor`/
  `reflection`/`extract_memory` take a model via `pick()`; `load_context`/`plan`
  do not.)
