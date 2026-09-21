---
type: architecture
title: Specialist sub-agents and the tool registry
description: How each of the five specialists (planner, concierge, journal, booking, budget) is compiled as a small ReAct subgraph with a trip guard, how the tool registry groups tools by domain and derives read-only/destructive metadata, how injected state and store arguments must be declared, the clarification and date-resolution tools, and how tool failures are classified so the model never narrates a deterministic fault as an outage.
tags: [subagents, react, tools, registry, injected-state, tool-errors, retry, clarification, date-resolution]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-18T04:47:06.927Z
sources:
  - id: openwiki-source-4dba2e7f175c0ab0085750ee
    resource: repo://apps/api/app/agents/retry.py
  - id: openwiki-source-0e29236b52482e5a3cdf5f04
    resource: repo://apps/api/app/agents/subagents/_base.py
  - id: openwiki-source-cc8c193e2cfd4461769ecfe7
    resource: repo://apps/api/app/agents/subagents/planner.py
  - id: openwiki-source-05334df1d43f03a9602e6170
    resource: repo://apps/api/app/core/dates.py
  - id: openwiki-source-53aa9f1963cc8720d5032ebb
    resource: repo://apps/api/app/tools/_base.py
  - id: openwiki-source-8ec461273059e7a8a78ffc8e
    resource: repo://apps/api/app/tools/clarification_tools.py
  - id: openwiki-source-aaa874e6e65dcc63bfc37509
    resource: repo://apps/api/app/tools/date_tools.py
  - id: openwiki-source-aae2f3ae4e0843e6715ef3ac
    resource: repo://apps/api/app/tools/memory_tools.py
  - id: openwiki-source-97b1fd4b365c73190c64c4c1
    resource: repo://apps/api/app/tools/registry.py
  - id: openwiki-source-b0025479938a9ecd6025a03f
    resource: repo://apps/api/tests/agents/test_subagent_fault_tolerance.py
  - id: openwiki-source-7c5d6ff98154df40e7163ba1
    resource: repo://apps/api/tests/agents/test_tool_error_classification.py
  - id: openwiki-source-827a5601a0a66b0a5f322177
    resource: repo://apps/api/tests/agents/test_trip_guard.py
  - id: openwiki-source-874d3e2f46ad3afec7649d3a
    resource: repo://apps/api/tests/tools/test_clarification_tools.py
  - id: openwiki-source-a2a23a764d4745867a521fec
    resource: repo://apps/api/tests/tools/test_tool_registry.py
generated: { by: "claude-code", at: "2026-09-18T04:47:06.927Z" }
---

# Specialist sub-agents and the tool registry

The supervisor never calls a tool itself. It routes each task to one of five **specialists**, each a compiled LangGraph subgraph built by `build_subagent` in `apps/api/app/agents/subagents/_base.py` and added to the parent graph as a node (see [Agent graph and supervisor routing](graph-and-supervisor.md)). The parent's checkpointer and store propagate into the subgraph, so tools that need the long-term store receive it without extra wiring.

## Anatomy of a specialist

Each builder (`planner.py`, `concierge.py`, `journal.py`, `booking.py`, `budget.py`) is one call: `build_subagent(name, get_tools_for(name), resolve_model, registry.get(name), tool_fault=...)`. The compiled subgraph has three nodes:

- **`assistant`** — resolves the chat model per request through the deferred resolver, filters out the episodic-recall tool when `AgentContext.allow_episodic` is false, binds the remaining tools, and builds the system message in a fixed order: the shared `communication_style` guideline plus the domain prompt (fixed at build), then the summary and memory blocks, the reply-language rule, the current-date grounding, and finally the supervisor's per-turn task note, so the cacheable prefix is identical across single-intent and fan-out turns on the same day (see [Agent state, runtime context and reply language](state-context-and-language.md) and [Prompt registry and versioning](prompt-registry.md)). It carries `LLM_RETRY`.
- **`trip_guard`** — entered only when the assistant emitted a call to a tool that needs an active trip and `state["trip_id"]` is empty. The set of such tools is **derived from annotations**, not hand-maintained: `_tools_needing_trip` inspects each tool's type hints for an `InjectedState("trip_id")` marker, so a new trip-scoped tool is covered the day it is written. A tool whose annotations cannot be read is excluded with a warning rather than blocking graph build. When it blocks, it emits an error `ToolMessage` for every pending call (the provider rejects unpaired calls), sets `awaiting_user=True`, and returns to the assistant so the traveller is asked which trip they mean.
- **`tools`** — a `ToolNode` over the domain tools, edged back to `assistant`.

The conditional edge after `assistant` decides the same thing the guard would decide one step earlier, so a round with no trip-scoped call goes straight to `tools`; visiting the guard every round would spend a super-step and shrink the tool-round budget under `agent_recursion_limit`.

`tests/agents/test_subagents.py` builds every specialist with a `FakeLLM` and checks a scripted answer; `test_trip_guard.py` checks that injected-`trip_id` tools are detected, that the guard passes through with an active trip, and that it blocks and sets `awaiting_user` without one.

## The tool registry

`app/tools/registry.py` is the single source of truth. `TOOLS_BY_DOMAIN` maps each specialist to a concatenation of tool groups from the domain modules (`trip_tools`, `place_tools`, `flight_tools`, `hotel_tools`, `booking_tools`, `expense_tools`, `weather_tools`, `climate_tools`, `routing_tools`, `visa_tools`, `tip_tools`, `rag_tools`, `memory_tools`, `date_tools`). The split encodes product rules that tests pin:

- **The planner searches but never books.** It gets flight *search* and hotel *availability* tools plus `create_trip`, but the money tools (`book_*`, `cancel_*`) live only in the HITL-gated `booking` domain (`test_planner_never_binds_destructive_tools`, `test_create_trip_bound_to_planner_only`).
- Hotel tools are split into search, availability and booking groups so the concierge can recommend without exposing booking.
- `recall_past_trips` is bound to the planner only; budget tools are bound to the budget specialist only; the concierge is the only specialist with the knowledge (RAG) tool.

`ALL_TOOLS` de-duplicates by name across domains, and `TOOL_METADATA` derives two flags per tool: `readOnly` (not in the `_WRITE` set) and `destructive` (one of `book_hotel`, `book_flight`, `cancel_flight`, `cancel_hotel`). These flags drive the MCP server's annotations and exclusions (see [MCP server exposure](../integrations/mcp-server.md)). `get_tools_for(domain)` returns an empty list for an unknown domain.

## Injected arguments must be declared

Many tools take `user_id`, `trip_id`, `messages` (via `InjectedState`), the `store` (via `InjectedStore`) or the `tool_call_id` (via `InjectedToolCallId`). All tools in this codebase use an explicit `args_schema`, and the schema **must declare the injected fields**: `ToolNode` derives its injection targets from the schema, so an injected parameter left out of it is never injected and the call fails with a missing-argument error. Declared fields are still stripped from the model-facing schema (`test_recall_past_trips_hides_injected_store_and_user_id`, `test_every_tool_has_explicit_described_schema`). Owner ids therefore never come from the model, which is what makes trip and booking tools ownership-safe.

Shared helpers in `app/tools/_base.py`: `session_scope()` yields a short-lived session per tool call with commit/rollback/close; `tool_error(AppError)` folds a domain error into a `ToolException` while preserving the `hint`; `log_tool_call` logs parameters with a redaction backstop; `dump` normalizes Pydantic results; `panel_result` builds the `(summary, artifact)` pair for side-panel tools and raises a non-recoverable error for an unknown panel kind. `_idempotency.py` scopes write-tool idempotency keys to one traveller turn so a reflection re-run replays rather than double-books, and `_ranking.py` re-ranks hotel and flight results by stated preferences in a stable, boost-only way (see [Bookings, flights and hotels](../domain/bookings-flights-and-hotels.md)).

## Control-flow tools

**`needs_clarification`** (`app/tools/clarification_tools.py`) is appended to every specialist's tool list inside `build_subagent`, deliberately *not* registered in the registry so it stays off MCP and the manifest. It returns a `Command` that sets `awaiting_user=True` and emits the paired `ToolMessage`; reflection then ends the turn and the remaining queued work is dropped (see the graph page). Tests confirm it stays out of the registry.

**`resolve_date`** (`app/tools/date_tools.py`) implements "the LLM parses, code computes": numeric and ISO forms take a zero-token fast path through `parse_numeric_date`; anything else is sent to the `date_resolution` model, which returns a structured `DateIntent`, and `compute_from_intent` does the arithmetic anchored to the calendar week. Ambiguity, a date in the past, or a provider failure become a `ToolException` that tells the model to ask the traveller for a concrete date. "Today" is grounded on the per-request traveller timezone from the runtime context so it matches the system prompt, falling back to `AGENT_TIMEZONE`. The tool is bound to the planner, concierge and booking domains.

## Tool-failure classification and retries

`app/agents/retry.py` makes the graph the single owner of retries (the LLM client sets SDK `max_retries=0`, see [LLM providers and per-agent configuration](llm-providers-and-agent-config.md)):

- `LLM_RETRY` retries transient provider errors identified by status code (408/409/429/5xx), `httpx` timeouts and connection errors, or SDK exception class *names*, so the agent layer never imports a provider SDK.
- The planner and concierge, which call real I/O (weather, routing), are built with `TOOL_FAULT`: the tools node retries only `UpstreamError` (`TRANSIENT_RETRY`), catches wrapped logic errors as messages, and after exhaustion `graceful_fallback` emits one `ToolMessage` per pending call and routes back to the assistant. The fallback wording is chosen by the failure class: an upstream cause gets "temporarily unavailable, try again shortly", anything else gets an explicit "not temporary, do not retry" message, because an outage that cannot be evidenced must not be claimed.
- The other specialists use a broad handler that catches every tool exception (LangGraph's default only catches argument-validation errors and would otherwise let a `ToolException` 500 the stream).

Both handlers render the message through `describe_tool_failure`, the single source of truth for the verdict. It distinguishes invalid model-supplied arguments ("fix them and call again"), a missing injected argument ("not an outage, retrying fails identically, ask the traveller"), an upstream error ("temporary, tell the user to try shortly"), a domain `AppError` on the cause chain ("a definite answer about the data, use the hint"), a bare `ToolException` ("the tool's own explanation, self-correct if you can"), and an unknown cause ("do not claim an outage and do not retry blindly"). This matters because a wrong verdict loops forever or asks the model for something it cannot supply (issue #113). `tests/agents/test_tool_error_classification.py` covers each branch and `test_subagent_fault_tolerance.py` covers retry-then-succeed and graceful exhaustion.

## Adding a tool

Write it in the matching `app/tools/<domain>_tools.py` with an explicit, described `args_schema` that declares any injected fields, raise `tool_error(e)` for domain errors, add it to the right group so the registry picks it up, and add it to `_WRITE` or `_DESTRUCTIVE` if it mutates data. If it makes its own LLM call, give it a config row name (see the coverage test on the LLM page). Trip-scoped tools need no registration with the guard; the `InjectedState("trip_id")` annotation is the registration.
