# gh-125 — Research Brief

Depth: **Standard** (intake lane `normal` → Standard per `rules/research-depth.md`). Not upgraded.
Re-run after evidence: no Deep signal appeared — no migration/schema, no auth or session scope, no
new dependency, no high-blast file, one changed source file. External surface **does** exist (the
fix relies on version-specific `langgraph` behavior), so official docs were required and checked.

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **Use built-in** — adopt LangGraph's existing optional-injected-state tolerance by giving `trip_id` a default, and return the "no active trip" guidance as an ordinary tool return value. |
| **Why this is the lightest credible path** | The tolerance already exists in the installed library and the "plain return becomes a `ToolMessage`" behavior is core `ToolNode` contract, so the whole fix is a signature change plus one guard per tool in a single file. |
| **Confidence** | 90% — mechanism proven by running it on the installed stack; the residual 10% is that the tolerance is keyed off a private attribute (see Risks). |
| **Next step** | `writing-plans` on `design.md`; first task should land the graph-level regression test that pins the behavior. |

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | pnpm + Turborepo monorepo; FastAPI backend (`apps/api/`), Next.js frontend (`apps/web/`) |
| Primary language + runtime | Python — 3.14 in the local `.venv`, **3.12 in Docker** (`docs/solutions/` records this split) |
| Frameworks / platforms | FastAPI, SQLAlchemy 2.x, LangGraph, LangChain |
| Relevant packages | `langgraph`, `langchain-core`, `mcp` (FastMCP) |
| Detectable versions | `apps/api/requirements-ai.txt:13` pins `langgraph>=1.0,<2.0`; installed locally **1.2.6**; issue reports **1.2.11** in Docker (container was down, so not re-confirmed) |
| Important constraints | `CLAUDE.md`: stage and commit as separate commands; PRs target the latest integration branch, not `main`. `rules/behavior.md`: surgical changes, no adjacent refactors. Branch isolation required before the first edit. |

## Feature Understanding and Assumptions

- **Requested feature:** stop `KeyError: 'trip_id'` from crashing any trip-scoped tool when the
  conversation has no active trip (GitHub issue #125).
- **What success appears to mean:** a turn like *"Please send my itinerary"* from `/trips` with
  `trip_id: null` produces a real reply — the agent asks which trip, or creates one and proceeds —
  instead of the generic error fallback.
- **Assumptions from the request:** the issue's own three-fact root-cause analysis is correct.
  All three were re-verified locally (see Evidence Ledger), so this is no longer an assumption.
- **Assumptions still needing confirmation:** that Docker's langgraph 1.2.11 behaves like the
  locally-installed 1.2.6 on the optional-injected-state path. The regression test in the plan is
  what settles this — it runs in the Docker suite via `make test-docker`.

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `apps/api/app/tools/trip_tools.py` — `InjectedState("trip_id")` at lines 49, 79, 107, 138, 181, each declared as a required `str`. |
| `Local` | `apps/api/app/routers/agent.py` `_turn_input()` — `if trip_id is not None:` guard; the deliberate omission from `specs/fix-trip-id-persist-across-turns`. |
| `Local` | `apps/api/app/agents/state.py:94` — `trip_id: str | None` declared but never written on a trip-less conversation. |
| `Local` | `apps/api/app/tools/registry.py:36,57,59` — the five tools are bound into three sub-agents: `planner`, `journal`, `budget`. |
| `Local` | `apps/api/app/agents/subagents/_base.py:141-150` — a sub-agent gets `_tool_error_to_message` unless it passes `tool_fault`; only `planner.py:27` and `concierge.py:27` pass `TOOL_FAULT`. So `journal` and `budget` relabel every `ToolException` as a transient outage (`_base.py:60-64`). |
| `Local` | `apps/api/app/mcp/server.py:39-40` — `if "store" in params or "tool_call_id" in params: continue`. Any tool given an `InjectedToolCallId` is silently dropped from the MCP server. |
| `Local` | `apps/api/tests/mcp/test_mcp_server.py:50-57` — asserts `create_trip` is excluded from MCP *because* it returns a `Command` + takes `tool_call_id`, while `get_trip_summary` is exposed. |
| `Local` | `apps/api/app/prompts/communication_style/v8.md:131` — "Never call `needs_clarification` because a tool failed or returned nothing." |
| `Local` | `docs/solutions/agent/explicit-args-schema-breaks-tool-injection.md` — injection targets are derived from the tool's *schema*; keep the auto-derived schema and describe injected args inline. The planned change stays inside that rule (it edits the signature, not `args_schema`). |
| `Local` | `docs/solutions/harness/formatter-strips-unused-import.md` — the PostToolUse ruff hook strips an import added before its first use. Relevant: this change adds no import, but any implementer adding one must land import + usage in a single edit. |
| `Upstream` | `langgraph/prebuilt/tool_node.py:1394-1397` — `elif tool_arg not in injected._optional_state_args: raise KeyError(state_field)`. |
| `Upstream` | `langgraph/prebuilt/tool_node.py:2008-2012` — membership in `_optional_state_args` is decided by exactly one condition: `field_info and not field_info.is_required()`. |
| `Upstream` | GitHub issues #6241, #6350 (langgraph) and #31688 (langchain) show recurring churn around `InjectedState` schema/required handling — reason to pin our behavior with a test rather than trust it implicitly. |
| `Docs` | `docs.langchain.com/oss/python/langgraph/workflows-agents` — the currently-recommended way to read graph state from a tool is the `ToolRuntime` argument, not `InjectedState`. Optional/defaulted `InjectedState` is not documented either way. |
| `Inference` | Because the docs do not describe the optional-injection tolerance, it should be treated as an undocumented implementation detail within the `>=1.0,<2.0` pin, guarded by our own regression test. |

## Local Findings

- **Relevant files:** `app/tools/trip_tools.py` (the only file the design changes),
  `app/tools/registry.py`, `app/agents/subagents/_base.py`, `app/agents/retry.py`,
  `app/mcp/server.py`, `tests/tools/test_trip_tools.py`, `tests/tools/test_tool_registry.py`,
  `tests/mcp/test_mcp_server.py`.
- **Existing abstractions / extension points:** `tool_error(e)` for domain failures with a `hint`
  (`app/tools/_base.py`); `session_scope()` for the tool's own unit of work; the auto-derived
  schema convention for injection-bearing tools.
- **Conventions worth preserving:** no hand-authored `args_schema` on injection-bearing tools;
  model-facing descriptions inline via `Annotated[..., Field(description=...)]`; keep the internal
  trip UUID out of `tool_call_schema`.
- **What can be reused:** everything — no new helper beyond a five-line `_no_active_trip()`.
- **What appears missing locally:** any test that exercises a trip tool with the `trip_id` channel
  absent. That gap is exactly why this shipped; the plan closes it.

## Upstream Findings

- **Repositories inspected:** `langchain-ai/langgraph` — the installed `prebuilt/tool_node.py`, plus
  issues #6241, #6350; `langchain-ai/langchain` issue #31688.
- **Pattern already present upstream:** optional injected state. `_infer_injected_args` marks any
  `InjectedState` parameter whose pydantic field is not required, and `_inject_tool_args` skips a
  missing state key for exactly those parameters instead of raising.
- **Areas worth modeling:** none beyond that — the fix consumes the capability rather than copying
  a pattern.
- **How closely it matches:** exactly. Our five tools are the "required" branch of that same code
  path; giving them a default moves them to the tolerated branch.
- **Upstream gaps / uncertainties:** the tolerance lives behind a private, underscore-prefixed
  attribute and the surrounding area has open bugs, so it carries no compatibility promise.

## Docs Findings

- **Official sources checked:** `docs.langchain.com/oss/python/langgraph/workflows-agents`;
  `reference.langchain.com/python/langgraph.prebuilt/tool_node/InjectedState`.
- **Version-matched vs latest-stable:** docs are for the LangGraph 1.x line, matching the
  `>=1.0,<2.0` pin. Local install is 1.2.6; Docker reports 1.2.11 (unverified this session).
- **Built-in capabilities that already support the feature:** two — optional injected state
  (undocumented), and `ToolNode` wrapping any non-`Command` tool return into a `ToolMessage`
  with the correct `tool_call_id` (core, documented behavior).
- **Current recommended APIs:** `ToolRuntime[Context, State]`, whose `runtime.state` is a plain
  dict read, so `state.get("trip_id")` could never raise. See Recommendation for why this is not
  the path here.
- **Caveats:** the docs do not mention defaulted `InjectedState` parameters at all, so the
  behavior is confirmed by source and by execution, not by documentation.

## Recommendation

- **Primary recommendation:** **use built-in.** Give `trip_id` a default so LangGraph's existing
  tolerance applies, and return a plain guidance dict (not a `Command`, not a raise) so
  `ToolNode` builds the `ToolMessage` and `handle_tool_errors` is never consulted.
- **Why this is the lightest credible path:** it changes one file, adds no parameter, no import,
  and no dependency; it leaves `_turn_input`, state, the supervisor, and every prompt untouched,
  which is what makes re-introducing `specs/fix-trip-id-persist-across-turns` structurally
  impossible; and both mechanisms were executed on the installed stack before being recommended.
- **Why the next-best alternative lost:** migrating the five tools to `ToolRuntime` is the
  officially recommended API and would make the missing key a non-issue by construction — but the
  parameter would be named `runtime`, and `app/mcp/server.py:39-40` only skips `store` and
  `tool_call_id`, so a runtime-bearing tool would be advertised over MCP with an unservable
  parameter. That is a larger, riskier change than the bug warrants; it belongs in a dedicated
  migration, not in a bug fix.
- **What would change this recommendation:** if the regression test fails on Docker's langgraph
  1.2.11, the optional-injection tolerance is not dependable across the pin range, and the fix
  should fall back to seeding the channel in `load_context_node` (recorded as the rejected
  alternative in `design.md`) — which is version-independent.

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:** (1) `_optional_state_args` is private and undocumented — a minor langgraph
  bump inside `>=1.0,<2.0` could change it; the graph-level regression test is the tripwire.
  (2) `list_trip_places` widens to `list | dict`. (3) Parameter reorder is safe for every call
  site found (all keyword-based) but would break a positional caller.
- **Evidence gaps:** the Docker container was not running this session, so langgraph 1.2.11 was
  not exercised directly; all library evidence comes from the local 1.2.6 install and its source.
- **Version uncertainties:** local 3.14 / Docker 3.12 and 1.2.6 / 1.2.11 splits. `make test-docker`
  is the reconciling check and must be in the plan's verification.
- **Follow-up questions for the user:** none. Both open forks (mechanism, UX) were decided during
  brainstorming.

## Source Pack

- **Local files read:** `apps/api/app/tools/trip_tools.py`, `apps/api/app/tools/_base.py`,
  `apps/api/app/tools/registry.py`, `apps/api/app/tools/clarification_tools.py`,
  `apps/api/app/routers/agent.py`, `apps/api/app/agents/state.py`, `apps/api/app/agents/nodes.py`,
  `apps/api/app/agents/retry.py`, `apps/api/app/agents/subagents/_base.py`,
  `apps/api/app/agents/subagents/planner.py`, `apps/api/app/agents/subagents/journal.py`,
  `apps/api/app/agents/subagents/budget.py`, `apps/api/app/agents/subagents/synthesis_worker.py`,
  `apps/api/app/mcp/server.py`, `apps/api/app/prompts/communication_style/v8.md`,
  `apps/api/tests/tools/test_trip_tools.py`, `apps/api/tests/tools/test_tool_registry.py`,
  `apps/api/tests/mcp/test_mcp_server.py`, `apps/api/requirements-ai.txt`,
  `docs/solutions/INDEX.md`, `docs/solutions/agent/explicit-args-schema-breaks-tool-injection.md`,
  `docs/solutions/harness/formatter-strips-unused-import.md`,
  `docs/solutions/harness/public-contract-gate-warn-only.md`,
  `specs/fix-trip-id-persist-across-turns/SUMMARY.md`,
  `.venv/lib/python3.14/site-packages/langgraph/prebuilt/tool_node.py`
- **Upstream repositories or pages checked:**
  - https://github.com/langchain-ai/langgraph/issues/6241
  - https://github.com/langchain-ai/langgraph/issues/6350
  - https://github.com/langchain-ai/langchain/issues/31688
- **Official docs domains or pages checked:**
  - https://docs.langchain.com/oss/python/langgraph/workflows-agents
  - https://reference.langchain.com/python/langgraph.prebuilt/tool_node/InjectedState

## Evidence Boundary

> **Confirmed from artifacts:** the five `InjectedState("trip_id")` sites and their required-`str`
> declaration; `_turn_input`'s conditional omission; `trip_id: str | None` in state; the
> sub-agent → `handle_tool_errors` mapping for `planner` / `journal` / `budget`; the MCP skip
> condition and the test that pins it; the `_optional_state_args` mechanism in the installed
> library source.
>
> **Confirmed by execution (run this session, langgraph 1.2.6):** required `InjectedState` +
> missing channel raises `KeyError: 'trip_id'`; the same tool with a default returns normally;
> a plain dict return becomes a `status="success"` `ToolMessage` with the `tool_call_id` paired,
> without consulting a deliberately mislabelling `handle_tool_errors`; `tool_call_schema` stays
> empty in every variant, so `trip_id` is never model-facing.
>
> **Inferred from patterns:** that Docker's langgraph 1.2.11 behaves identically on this path;
> that no positional caller of the five tools exists outside the paths searched.
>
> **Not checked:** the running Docker stack (container down); the live end-to-end repro from the
> issue; whether any frontend code depends on the current error-fallback behavior.
