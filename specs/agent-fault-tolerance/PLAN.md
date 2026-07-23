---
slug: agent-fault-tolerance
status: shipped
owner: Minh Tran
created: 2026-07-03
linear: MIN-49
---

# Agent Fault-Tolerance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans (or subagent-driven-development) to implement this plan task-by-task.

**Goal:** Give the agent graph LangGraph `RetryPolicy` on all real LLM calls + a transient-vs-logic tool-error split (with graceful degradation) on the weather/routing tool paths, without regressing today's error UX.

**Architecture:** A new `app/agents/retry.py` holds the two policies, a duck-typed LLM-retry predicate, a narrowed tool-error handler, a `graceful_fallback` node `error_handler`, and a `ToolFaultPolicy` bundle. `build_subagent` always retries its `assistant` node and takes an optional `tool_fault` (only concierge/planner pass it — booking/budget/journal keep today's catch-all handler, no retry). Weather/routing tools re-raise `UpstreamError` unwrapped so `RetryPolicy` fires; `graph.py` retries the four top-level LLM nodes; `clients/llm.py` sets SDK `max_retries=0` so the graph is the single retry owner.

**Tech Stack:** Python 3.10+, FastAPI, LangGraph 1.2.6, LangChain 1.3.11 (`init_chat_model`), pytest (async via `asyncio.run(...)`), `FakeLLM` test double.

**Verified facts (research-brief.md):** `RetryPolicy` is a NamedTuple whose defaults already equal our params (`initial_interval=0.5, backoff_factor=2, max_interval=128, max_attempts=3, jitter=True`). `NodeError` (`langgraph.errors`, fields `.node`, `.error`). `ToolNode` narrows caught types from the handler's first-param annotation (`_infer_handled_types`), so annotating `exc: ToolException` lets `UpstreamError` propagate. SDKs retry ~2× by default → we set `max_retries=0`.

**Key conventions:**
- Run tests from `apps/api/`: `../../.venv/bin/python -m pytest <path> -x -q`.
- The `ruff-on-edit` hook strips imports added before their use — **add each import together with its first usage** in the same edit, then run `ruff check app` before tests.
- No schema change → no `travel.db` rebuild needed.
- Tests that assert retry timing use a **zero-interval** `RetryPolicy` in-test to stay fast; production `TRANSIENT_RETRY` keeps `initial_interval=0.5`.

---

## File Structure

| File | Responsibility | Create/Modify |
|---|---|---|
| `app/agents/retry.py` | Policies, predicate, handlers, `ToolFaultPolicy`, `TOOL_FAULT` | **Create** |
| `app/agents/subagents/_base.py` | `assistant` retry; optional `tool_fault` on `tools` node | Modify |
| `app/agents/subagents/concierge.py` | Pass `tool_fault=TOOL_FAULT` | Modify |
| `app/agents/subagents/planner.py` | Pass `tool_fault=TOOL_FAULT` | Modify |
| `app/tools/weather_tools.py` | Re-raise `UpstreamError` (3 sites) | Modify |
| `app/tools/routing_tools.py` | Re-raise `UpstreamError` (2 sites) | Modify |
| `app/agents/graph.py` | `retry_policy=LLM_RETRY` on 4 top-level LLM nodes | Modify |
| `app/clients/llm.py` | SDK `max_retries=0` (single retry owner) | Modify |
| `tests/agents/test_retry.py` | Unit: predicate + `graceful_fallback` + policies | **Create** |
| `tests/tools/test_weather_tools.py` | Re-raise vs wrap behavior | Modify |
| `tests/tools/test_routing_tools.py` | Re-raise vs wrap behavior | Modify |
| `tests/agents/test_subagent_fault_tolerance.py` | Sub-agent LLM retry + tool retry + graceful exhaustion | **Create** |
| `tests/clients/test_llm_max_retries.py` | `max_retries=0` passed to `init_chat_model` | **Create** |

## Wave Plan

| Wave | Tasks | Parallel | Depends on |
|---|---|---|---|
| 1 | 1.1 `retry.py`, 1.2 tool re-raise | 2 parallel (disjoint files) | — |
| 2 | 2.1 `_base.py`, 2.2 `graph.py`, 2.3 `clients/llm.py` | 3 parallel (disjoint files) | retry.py (1.1) |
| 3 | 3.1 concierge + planner | single | `_base.py` new signature (2.1) |
| 4 | 4.1 sub-agent integration tests | single | all above |

---

## Chunk 1: Fault-tolerance implementation

### Task 1.1 — Create `app/agents/retry.py` (Wave 1)

**Files:**
- Create: `app/agents/retry.py`
- Test: `tests/agents/test_retry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/agents/test_retry.py
"""Unit tests for the fault-tolerance policies (specs/agent-fault-tolerance, MIN-49)."""

import httpx
from langchain_core.messages import AIMessage
from langgraph.errors import NodeError

from app.agents.retry import (
    GRACEFUL_MSG,
    LLM_RETRY,
    TRANSIENT_RETRY,
    _is_retryable_llm,
    graceful_fallback,
)
from app.exceptions import NotFoundError, WeatherUnavailableError


def test_is_retryable_llm_status_codes():
    assert _is_retryable_llm(type("E", (Exception,), {"status_code": 429})())
    assert _is_retryable_llm(type("E", (Exception,), {"status_code": 503})())
    assert not _is_retryable_llm(type("E", (Exception,), {"status_code": 400})())


def test_is_retryable_llm_httpx_and_name():
    assert _is_retryable_llm(httpx.ConnectError("boom"))
    assert _is_retryable_llm(type("APITimeoutError", (Exception,), {})())
    assert not _is_retryable_llm(ValueError("nope"))


def test_transient_retry_matches_only_upstream():
    assert TRANSIENT_RETRY.retry_on(WeatherUnavailableError("down"))
    assert not TRANSIENT_RETRY.retry_on(NotFoundError("missing"))


def test_llm_retry_keeps_default_backoff():
    assert LLM_RETRY.max_attempts == 3
    assert LLM_RETRY.retry_on is _is_retryable_llm


def test_graceful_fallback_one_message_per_tool_call():
    ai = AIMessage(
        content="",
        tool_calls=[
            {"name": "get_weather", "args": {}, "id": "c1", "type": "tool_call"},
            {"name": "get_route", "args": {}, "id": "c2", "type": "tool_call"},
        ],
    )
    cmd = graceful_fallback(
        {"messages": [ai]}, NodeError(node="tools", error=RuntimeError("x"))
    )
    msgs = cmd.update["messages"]
    assert [m.tool_call_id for m in msgs] == ["c1", "c2"]
    assert all(m.content == GRACEFUL_MSG for m in msgs)
    assert cmd.goto == "assistant"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_retry.py -x -q`
Expected: FAIL — `ModuleNotFoundError: app.agents.retry`.

- [ ] **Step 3: Write `app/agents/retry.py`**

```python
"""Fault-tolerance policies for the agent graph (specs/agent-fault-tolerance, MIN-49).

Central home for LangGraph retry/error-handling wiring so the graph is the single
retry owner. ``LLM_RETRY`` guards LLM provider calls (rate-limit/network) on every
LLM node; ``TOOL_FAULT`` (retry + narrowed handler + graceful fallback) guards the
real-I/O tool nodes (concierge weather, planner routing). Transient failures are the
provider-agnostic ``UpstreamError`` family; logic failures stay ``ToolException``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx
from langchain_core.messages import ToolMessage
from langchain_core.tools import ToolException
from langgraph.errors import NodeError
from langgraph.types import Command, RetryPolicy

from app.exceptions import UpstreamError

# Shown to the user after transient retries are exhausted (or a non-retryable
# error surfaces). Mirrors today's tool-unavailable message, minus "do not retry".
GRACEFUL_MSG = (
    "The requested information is temporarily unavailable due to an upstream "
    "problem. Tell the user it could not be retrieved right now and to try again "
    "shortly."
)

# Provider-SDK exception class names that mean "transient" — matched by name so the
# agent layer never imports openai/anthropic (see app/clients/llm.py).
_RETRYABLE_LLM_NAMES = {"APIConnectionError", "APITimeoutError", "APIConnectionTimeoutError"}


def _is_retryable_llm(exc: Exception) -> bool:
    """True for transient LLM provider failures; provider-agnostic (no SDK import).

    :param exc: The exception raised by an LLM node.
    :return: Whether the call should be retried.
    """
    code = getattr(exc, "status_code", None)
    if code in (408, 409, 429) or (isinstance(code, int) and 500 <= code < 600):
        return True
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, ConnectionError)):
        return True
    return exc.__class__.__name__ in _RETRYABLE_LLM_NAMES


# All other RetryPolicy fields keep langgraph defaults (already equal to our params).
LLM_RETRY = RetryPolicy(retry_on=_is_retryable_llm)
TRANSIENT_RETRY = RetryPolicy(retry_on=lambda e: isinstance(e, UpstreamError))


def _tool_error_logic_only(exc: ToolException) -> str:
    """Narrowed ``handle_tool_errors`` for retry sub-agents.

    Annotation ``ToolException`` tells ToolNode to catch only wrapped logic errors;
    a re-raised ``UpstreamError`` is not a ``ToolException`` and propagates to the
    node's ``RetryPolicy``.

    :param exc: The wrapped logic error raised by a tool.
    :return: A message telling the model to self-correct its arguments.
    """
    return (
        f"Tool call failed: {exc}. The request looks invalid — check the arguments "
        "and try a corrected call, or tell the user what is needed."
    )


def graceful_fallback(state: dict, error: NodeError) -> Command:
    """tools-node ``error_handler``: restore graceful degradation after exhaustion.

    The failed ``tools`` node produced no ``ToolMessage`` for any pending call, so a
    provider would reject the next ``assistant`` turn. Emit one ``ToolMessage`` per
    pending ``tool_call_id`` (read from the last ``AIMessage``), then route back to
    ``assistant``.

    :param state: The graph state whose last message is the tool-calling AIMessage.
    :param error: The LangGraph failure context (``error.error`` is the exception).
    :return: A ``Command`` appending graceful tool messages and going to assistant.
    """
    last = state["messages"][-1]
    tool_calls = getattr(last, "tool_calls", None) or []
    msgs = [
        ToolMessage(
            content=GRACEFUL_MSG,
            tool_call_id=tc["id"],
            name=tc["name"],
            status="error",
        )
        for tc in tool_calls
    ]
    return Command(goto="assistant", update={"messages": msgs})


@dataclass(frozen=True)
class ToolFaultPolicy:
    """Bundle of the three tool-node fault-tolerance knobs that travel together."""

    retry_policy: RetryPolicy
    handle_tool_errors: Callable
    error_handler: Callable


# Shared bundle for the real-I/O sub-agents (concierge weather, planner routing).
TOOL_FAULT = ToolFaultPolicy(
    retry_policy=TRANSIENT_RETRY,
    handle_tool_errors=_tool_error_logic_only,
    error_handler=graceful_fallback,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_retry.py -x -q`
Expected: PASS (5 tests). Then `ruff check app/agents/retry.py`.

```xml
<task id="1.1" wave="1">
  <files>app/agents/retry.py, tests/agents/test_retry.py</files>
  <action>Create app/agents/retry.py with GRACEFUL_MSG, _is_retryable_llm, LLM_RETRY, TRANSIENT_RETRY, _tool_error_logic_only, graceful_fallback, ToolFaultPolicy, TOOL_FAULT exactly as in the code block. graceful_fallback MUST emit one ToolMessage per pending tool_call_id. No provider-SDK import.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_retry.py -x -q</verify>
  <done>5 unit tests pass; ruff clean; no openai/anthropic import.</done>
</task>
```

### Task 1.2 — Weather/routing tools re-raise `UpstreamError` (Wave 1)

**Files:**
- Modify: `app/tools/weather_tools.py` (3 sites: `get_weather`, `get_packing`, `get_air_quality`)
- Modify: `app/tools/routing_tools.py` (2 sites: `get_route`, `get_city_route`)
- Test: `tests/tools/test_weather_tools.py`, `tests/tools/test_routing_tools.py`

- [ ] **Step 1: Write the failing tests** (append to each file)

```python
# tests/tools/test_weather_tools.py — append
import asyncio

import pytest
from langchain_core.tools import ToolException

from app.exceptions import CityNotFoundError, UpstreamError, WeatherUnavailableError


def test_get_weather_reraises_upstream(monkeypatch):
    from app.tools import weather_tools

    async def boom(*a, **k):
        raise WeatherUnavailableError("open-meteo down")

    monkeypatch.setattr(weather_tools.weather_service, "get_weather", boom)
    with pytest.raises(UpstreamError):
        asyncio.run(weather_tools.get_weather.ainvoke({"city": "Paris"}))


def test_get_weather_wraps_logic(monkeypatch):
    from app.tools import weather_tools

    async def boom(*a, **k):
        raise CityNotFoundError("nope")

    monkeypatch.setattr(weather_tools.weather_service, "get_weather", boom)
    with pytest.raises(ToolException):
        asyncio.run(weather_tools.get_weather.ainvoke({"city": "Xyzzy"}))
```

```python
# tests/tools/test_routing_tools.py — append
import asyncio

import pytest
from langchain_core.tools import ToolException

from app.exceptions import RoutingUnavailableError, UpstreamError


def test_get_city_route_reraises_upstream(monkeypatch):
    from app.services import routing_service as rs_mod
    from app.tools import routing_tools

    async def boom(self, *a, **k):
        raise RoutingUnavailableError("ORS down")

    monkeypatch.setattr(rs_mod.RoutingService, "get_city_route", boom)
    with pytest.raises(UpstreamError):
        asyncio.run(
            routing_tools.get_city_route.ainvoke(
                {"origin_city": "Hanoi", "destination_city": "Da Nang"}
            )
        )
```

> **Executor note:** confirm the exact attribute names (`weather_tools.weather_service`, `RoutingService.get_city_route`) against the current tool files before running — patch the object the tool actually calls. If `air_quality_service`/`get_packing` use a different service handle, mirror the same pattern.

- [ ] **Step 2: Run to verify FAIL**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_weather_tools.py tests/tools/test_routing_tools.py -x -q -k "upstream or wraps"`
Expected: FAIL — `get_weather` currently wraps `WeatherUnavailableError` into `ToolException`, so `pytest.raises(UpstreamError)` fails.

- [ ] **Step 3: Edit the 5 tool sites**

For each of `get_weather`, `get_packing`, `get_air_quality` (weather_tools.py) and `get_route`, `get_city_route` (routing_tools.py), insert an `UpstreamError` re-raise **before** the existing `except AppError`:

```python
    try:
        r = await weather_service.get_weather(city, days)
    except UpstreamError:
        raise  # transient — let RetryPolicy retry the node
    except AppError as e:
        raise ToolException(str(e)) from e
```

Update each file's import in the **same edit**: `from app.exceptions import AppError` → `from app.exceptions import AppError, UpstreamError`.

> **Do NOT wrap `ValueError` here.** These tools validate args via `args_schema` and their services raise `AppError`, so a raw `ValueError` cannot originate here; if an unexpected non-`ToolException` did surface, `TRANSIENT_RETRY.retry_on` returns `False` for it and `graceful_fallback` still degrades it cleanly. Keeping the edit to the `UpstreamError` re-raise is surgical (behavior.md §3).

- [ ] **Step 4: Run to verify PASS**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_weather_tools.py tests/tools/test_routing_tools.py -x -q`
Expected: PASS (new + existing tool tests). Then `ruff check app/tools/weather_tools.py app/tools/routing_tools.py`.

```xml
<task id="1.2" wave="1">
  <files>app/tools/weather_tools.py, app/tools/routing_tools.py, tests/tools/test_weather_tools.py, tests/tools/test_routing_tools.py</files>
  <action>At all 5 tool try/except sites add `except UpstreamError: raise` before `except AppError`; add UpstreamError to each import in the same edit. Do not wrap ValueError. Append the re-raise/wrap tests.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_weather_tools.py tests/tools/test_routing_tools.py -x -q</verify>
  <done>Transient re-raises as UpstreamError; logic still wraps to ToolException; existing tool tests green.</done>
</task>
```

### Task 2.1 — Wire retry into `build_subagent` (Wave 2)

**Files:**
- Modify: `app/agents/subagents/_base.py`
- Test: `tests/agents/test_subagent_fault_tolerance.py`

- [ ] **Step 1: Write the failing test** (assistant-node LLM retry + narrowing smoke)

```python
# tests/agents/test_subagent_fault_tolerance.py
"""Sub-agent fault-tolerance wiring (specs/agent-fault-tolerance, MIN-49)."""

from langchain_core.messages import HumanMessage
from langchain_core.tools import ToolException
from langgraph.prebuilt.tool_node import _infer_handled_types
from langgraph.types import RetryPolicy
from pydantic import PrivateAttr

from app.agents.retry import ToolFaultPolicy, _tool_error_logic_only, graceful_fallback
from app.agents.subagents._base import build_subagent
from app.clients.llm import FakeLLM
from app.exceptions import WeatherUnavailableError

# Fast, zero-sleep policy for tests.
_FAST = RetryPolicy(retry_on=lambda e: isinstance(e, WeatherUnavailableError),
                    initial_interval=0.0, max_attempts=3)
_FAST_FAULT = ToolFaultPolicy(_FAST, _tool_error_logic_only, graceful_fallback)


class FlakyLLM(FakeLLM):
    fail_times: int = 1
    _calls: int = PrivateAttr(default=0)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._calls += 1
        if self._calls <= self.fail_times:
            err = RuntimeError("rate limited")
            err.status_code = 429
            raise err
        return super()._generate(messages, stop, run_manager, **kwargs)


def test_narrowed_handler_only_catches_toolexception():
    assert _infer_handled_types(_tool_error_logic_only) == (ToolException,)


def test_assistant_node_retries_transient_llm_error():
    flaky = FlakyLLM(fail_times=1, responses=["Paris is sunny"])
    sub = build_subagent("t", [], lambda _=None: flaky, "prompt")
    result = sub.invoke({"messages": [HumanMessage("weather in Paris")]})
    assert flaky._calls == 2  # failed once, retried, succeeded
    assert result["messages"][-1].content == "Paris is sunny"
```

- [ ] **Step 2: Run to verify FAIL**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_subagent_fault_tolerance.py -x -q`
Expected: FAIL — assistant node has no `retry_policy`, so the run raises `RuntimeError("rate limited")` instead of recovering.

- [ ] **Step 3: Edit `_base.py`**

Add imports (with usage, same edit): `from app.agents.retry import LLM_RETRY, ToolFaultPolicy`.

Change `build_subagent` signature to add a trailing keyword param:

```python
def build_subagent(
    name: str,
    tools: list[BaseTool],
    resolve_model: Callable[[str | None], BaseChatModel],
    prompt: str,
    tool_fault: ToolFaultPolicy | None = None,
):
```

Give the `assistant` node the LLM retry:

```python
    builder = StateGraph(TravelAgentState, context_schema=AgentContext)
    builder.add_node("assistant", assistant, retry_policy=LLM_RETRY)
    builder.add_edge(START, "assistant")
```

Replace the `tools` wiring block:

```python
    if tools:
        if tool_fault is None:
            builder.add_node(
                "tools", ToolNode(tools, handle_tool_errors=_tool_error_to_message)
            )
        else:
            builder.add_node(
                "tools",
                ToolNode(tools, handle_tool_errors=tool_fault.handle_tool_errors),
                retry_policy=tool_fault.retry_policy,
                error_handler=tool_fault.error_handler,
            )
        builder.add_conditional_edges("assistant", tools_condition)
        builder.add_edge("tools", "assistant")
    else:
        builder.add_edge("assistant", END)
```

Leave `_tool_error_to_message` unchanged (it stays the default catch-all for booking/budget/journal).

- [ ] **Step 4: Run to verify PASS**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_subagent_fault_tolerance.py -x -q`
Expected: PASS (2 tests). Then `ruff check app/agents/subagents/_base.py`.

```xml
<task id="2.1" wave="2">
  <files>app/agents/subagents/_base.py, tests/agents/test_subagent_fault_tolerance.py</files>
  <action>Add tool_fault param to build_subagent; add retry_policy=LLM_RETRY to the assistant node; branch the tools node on tool_fault (None → today's catch-all handler + no retry; set → narrowed handler + retry_policy + error_handler). Import LLM_RETRY, ToolFaultPolicy with usage. Leave _tool_error_to_message unchanged.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_subagent_fault_tolerance.py -x -q</verify>
  <done>Narrowed handler catches only ToolException; assistant node recovers a transient LLM error via retry.</done>
</task>
```

### Task 2.2 — Retry the top-level LLM nodes in `graph.py` (Wave 2)

**Files:**
- Modify: `app/agents/graph.py`

- [ ] **Step 1: Edit** — add import (with usage) `from app.agents.retry import LLM_RETRY`, then add `retry_policy=LLM_RETRY` to the four LLM `add_node` calls:

```python
    builder.add_node("summarize", make_summarize_node(pick("summarize")), retry_policy=LLM_RETRY)
    builder.add_node(
        "supervisor",
        make_supervisor(pick("supervisor")),
        destinations=(*SUBAGENTS, "plan", "__end__"),
        retry_policy=LLM_RETRY,
    )
    # ... reflection and extract_memory get retry_policy=LLM_RETRY too:
    builder.add_node(
        "reflection",
        make_reflection_node(pick("reflection")),
        destinations=(*SUBAGENTS, "extract_memory"),
        retry_policy=LLM_RETRY,
    )
    builder.add_node(
        "extract_memory", make_extract_memory_node(pick("extract_memory")), retry_policy=LLM_RETRY
    )
```

Do **not** add it to `load_context` or `plan` (no LLM call).

- [ ] **Step 2: Verify the graph still builds/green (targeted, <60s)**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_hitl_plan.py -q`
Expected: PASS — `test_hitl_plan.py` compiles the full `build_graph` (all four LLM nodes + sub-agents), so it proves the `retry_policy` kwargs don't break assembly. (Run the wider `tests/agents` in the Task 4.1 regression step.)

```xml
<task id="2.2" wave="2">
  <files>app/agents/graph.py</files>
  <action>Add retry_policy=LLM_RETRY to the summarize, supervisor, reflection, extract_memory add_node calls (import LLM_RETRY with usage). Leave load_context and plan untouched.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_hitl_plan.py -q</verify>
  <done>Four LLM nodes carry LLM_RETRY; full graph still compiles + smoke green.</done>
</task>
```

### Task 2.3 — Single retry owner: SDK `max_retries=0` in `clients/llm.py` (Wave 2)

**Files:**
- Modify: `app/clients/llm.py` (`_build_chat_model`)
- Test: `tests/clients/test_llm_max_retries.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/clients/test_llm_max_retries.py
"""_build_chat_model disables SDK-level retry so the graph is the single owner."""

from app.clients import llm as llm_mod


def test_build_chat_model_sets_max_retries_zero(monkeypatch):
    captured = {}

    def fake_init(model, **kwargs):
        captured.update(kwargs)
        captured["model"] = model
        return object()

    monkeypatch.setattr(llm_mod, "init_chat_model", fake_init)
    llm_mod._build_chat_model("openai", "gpt-4o")
    assert captured["max_retries"] == 0
```

- [ ] **Step 2: Run to verify FAIL**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/clients/test_llm_max_retries.py -x -q`
Expected: FAIL — `KeyError: 'max_retries'`.

- [ ] **Step 3: Edit `_build_chat_model`** — set the default before the `init_chat_model` call:

```python
    if temperature is not None:
        kwargs["temperature"] = temperature

    kwargs.setdefault("max_retries", 0)  # graph owns retry (MIN-49); avoid SDK double-retry

    return init_chat_model(model, model_provider=profile.sdk, streaming=True, **kwargs)
```

- [ ] **Step 4: Run to verify PASS**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/clients/test_llm_max_retries.py -x -q`
Expected: PASS. Then `ruff check app/clients/llm.py`.

```xml
<task id="2.3" wave="2">
  <files>app/clients/llm.py, tests/clients/test_llm_max_retries.py</files>
  <action>In _build_chat_model, kwargs.setdefault("max_retries", 0) before init_chat_model so provider SDKs do not double-retry under the graph's LLM_RETRY.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/clients/test_llm_max_retries.py -x -q</verify>
  <done>init_chat_model receives max_retries=0; FakeLLM path unaffected.</done>
</task>
```

### Task 3.1 — concierge + planner opt into `TOOL_FAULT` (Wave 3)

**Files:**
- Modify: `app/agents/subagents/concierge.py`
- Modify: `app/agents/subagents/planner.py`

- [ ] **Step 1: Edit both** — import (with usage) `from app.agents.retry import TOOL_FAULT`, pass it as the `tool_fault` kwarg:

```python
# concierge.py
    return build_subagent(
        "concierge",
        get_tools_for("concierge"),
        resolve_model,
        registry.get("concierge"),
        tool_fault=TOOL_FAULT,
    )
```

```python
# planner.py
    return build_subagent(
        "planner",
        get_tools_for("planner"),
        resolve_model,
        registry.get("planner"),
        tool_fault=TOOL_FAULT,
    )
```

- [ ] **Step 2: Verify graph builds with concierge/planner rewired (targeted, <60s)**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_hitl_plan.py -q`
Expected: PASS — the graph builds concierge/planner via `build_subagent(..., tool_fault=TOOL_FAULT)`; a broken signature/import fails compilation here.

```xml
<task id="3.1" wave="3">
  <files>app/agents/subagents/concierge.py, app/agents/subagents/planner.py</files>
  <action>Pass tool_fault=TOOL_FAULT to build_subagent in build_concierge and build_planner (import TOOL_FAULT with usage). booking/budget/journal remain unchanged.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_hitl_plan.py -q</verify>
  <done>Only concierge/planner carry the tool-fault policy; suite green.</done>
</task>
```

### Task 4.1 — Tool retry + graceful-exhaustion integration (Wave 4)

**Files:**
- Test: `tests/agents/test_subagent_fault_tolerance.py` (append)

- [ ] **Step 1: Append the failing tests**

```python
# tests/agents/test_subagent_fault_tolerance.py — append
# (merge `tool` into the existing `from langchain_core.tools import ToolException` line)
from langchain_core.tools import tool


def _flaky_weather_tool(counter: dict, fail_times: int):
    @tool
    def flaky_weather(city: str) -> str:
        """Get the weather for a city."""
        counter["n"] += 1
        if counter["n"] <= fail_times:
            raise WeatherUnavailableError("open-meteo down")
        return f"Weather in {city}: sunny"

    return flaky_weather


def _tool_calling_llm():
    return FakeLLM(
        responses=[
            {"content": "", "tool_calls": [
                {"name": "flaky_weather", "args": {"city": "Paris"}, "id": "c1", "type": "tool_call"}
            ]},
            "Done — told the user.",
        ]
    )


def test_tools_node_retries_then_succeeds():
    counter = {"n": 0}
    tool_ = _flaky_weather_tool(counter, fail_times=2)  # fail 2, succeed on attempt 3
    sub = build_subagent("t", [tool_], lambda _=None: _tool_calling_llm(),
                         "prompt", tool_fault=_FAST_FAULT)
    result = sub.invoke({"messages": [HumanMessage("weather in Paris")]})
    assert counter["n"] == 3  # 1 initial + 2 retries (max_attempts=3)
    assert result["messages"][-1].content == "Done — told the user."


def test_tools_node_graceful_after_exhaustion():
    from app.agents.retry import GRACEFUL_MSG

    counter = {"n": 0}
    tool_ = _flaky_weather_tool(counter, fail_times=99)  # always fails
    sub = build_subagent("t", [tool_], lambda _=None: _tool_calling_llm(),
                         "prompt", tool_fault=_FAST_FAULT)
    result = sub.invoke({"messages": [HumanMessage("weather in Paris")]})
    assert counter["n"] == 3  # exhausted after max_attempts
    graceful = [m for m in result["messages"] if getattr(m, "content", None) == GRACEFUL_MSG]
    assert graceful and graceful[0].tool_call_id == "c1"  # no 500; graceful ToolMessage emitted
```

- [ ] **Step 2: Run to verify PASS**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_subagent_fault_tolerance.py -x -q`
Expected: PASS (4 tests total in the file). If retry sleeps make it slow, confirm `_FAST` uses `initial_interval=0.0`.

- [ ] **Step 3: Full regression**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/agents tests/tools tests/clients -q`
Expected: PASS. (Booking/budget/journal unchanged → their error UX is preserved; no 500 regression.)

> **Env caveat:** if local `apps/api/.env` sets `OPENAI_API_KEY=test`, a handful of unrelated real-LLM/RAG tests fail (memory: `env-openai-key-test-breaks-llm-tests`) — move `.env` aside for a fully green run. The tests in this plan use `FakeLLM`/monkeypatch and are unaffected.

```xml
<task id="4.1" wave="4">
  <files>tests/agents/test_subagent_fault_tolerance.py</files>
  <action>Append integration tests: a flaky tool that fails twice then succeeds proves the tools node retried 3× and the run completed; a tool that always fails proves graceful_fallback emits a GRACEFUL_MSG ToolMessage per tool_call_id with no exception (no 500). Use the zero-interval _FAST_FAULT for speed.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents tests/tools tests/clients -q</verify>
  <done>Tool retry fires + recovers; exhaustion degrades gracefully; full agent/tools/clients suite green.</done>
</task>
```

---

## Risks

- **Retry sleep in tests** — use the zero-interval `_FAST` policy in-test; production `TRANSIENT_RETRY`/`LLM_RETRY` keep `initial_interval=0.5` + jitter, bounded by `max_attempts=3`, `max_interval=128`.
- **`error_handler` `Command(goto="assistant")` routing** — ✅ **verified unnecessary to hint.** Empirical repro on langgraph 1.2.6: an `error_handler` returning `Command(goto="assistant", update=…)` routes correctly with only the static `add_edge("tools","assistant")`, and `assistant` runs exactly once (no double-run). No `destinations=` needed.
- **`_infer_handled_types` import path** — `from langgraph.prebuilt.tool_node import _infer_handled_types` is an internal symbol (verified present in 1.2.6); if a future bump moves it, assert narrowing behaviorally instead (feed a `ToolException` and an `UpstreamError` through a built sub-agent).
- **Routing test touches the DB** — `get_city_route.ainvoke` enters the real `session_scope()` (SQLite) before the mocked `RoutingService.get_city_route` raises. Harmless inside the seeded suite; noted so the executor isn't surprised it's not fully in-memory like the weather test.
- **SDK `max_retries=0` on an unknown provider** — `init_chat_model` forwards `max_retries` to the provider chat class; all four configured providers accept it. A bare/unknown provider profile that rejects it would raise at construction — acceptable and loud.

## Status Log

- 2026-07-03 — Plan drafted from design.md + research-brief.md (all forks/open items resolved: SAGA dropped, TimeoutPolicy deferred, decision B for LLM retry).
- 2026-07-03 — All 7 tasks (waves 1-4) implemented on branch `feat/agent-fault-tolerance` (off `v3`), via executing-plans skill. Waves 1 and 2 dispatched as parallel subagents (1.1/1.2, then 2.1/2.2/2.3); waves 3 and 4 executed directly (single-task waves). Full regression green (253 tests, `tests/agents tests/tools tests/clients`). Two deviations recorded in `SUMMARY.md` (stale pre-existing test + plan test-fixture bug, both Rule 1).
- 2026-07-03 — shipped via `feat/agent-fault-tolerance` (commit `d059bb6`); PR opening against `v3`.
