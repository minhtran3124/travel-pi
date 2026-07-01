# standardize-tool-args-schema — Summary

Lane: high-risk
Confidence: high
Reason: Broad sweep across ~27 tools in 11 domain files touching the model-visible + MCP-exposed tool-calling contract (flags 6, 8, 9, 10); no hard gate fired.
Flags: public-contracts, existing-behavior, weak-proof, multi-domain
Affects: app/tools/* (agent tool-calling contract), app/mcp/server.py (external MCP tool surface)
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

Linear MIN-46 — "Standardize args_schema across all tools in app/tools/".

Goal: Review and standardize `args_schema` (Pydantic) for all tools registered in `app/tools/`
(via `registry.py`), to reduce the model hallucinating/guessing tool parameters.

Context: Some tools currently use plain type hints (`str`, `int`, etc.) instead of an explicit
`args_schema`, making it easier for the model to guess wrong values or invent params that don't
exist. We need to bring all tools to a consistent schema standard.

Scope:
- List all existing tools in `app/tools/` (by domain) and flag which ones don't yet have a dedicated `args_schema`
- For each tool: define an explicit Pydantic `args_schema` with `Field(..., description=...)` for every param
- Replace free-form `str` with `Literal`/`Enum` for params that have a finite set of valid values (status, unit, operator...)
- Clearly mark required vs optional (default) for each field
- Add an `args_schema.model_validate(...)` validation step before executing the actual tool (if the current graph node doesn't already have this)
- Update tool docstrings/descriptions to match the new schema
- Review tools exposed via the MCP surface (`app/mcp/`) to ensure schemas stay in sync when exposed externally

Out of scope: Adding new tools; changing business logic inside `_run`/`_arun`.

Notes: Related to MIN-42 (Implement MCP tool) — coordinate so any new tool created there already
follows this schema standard from the start.

## What changed

<pending implementation — intake only>

### Rationale

High-risk lane assigned on flag count (4: public-contracts, existing-behavior, weak-proof,
multi-domain), not on a hard gate. The blast radius is breadth, not depth: ~27 tools across 11
domains all share the LLM tool-calling contract, and a subset is re-exposed through the MCP
server, so a schema regression is model-visible and client-visible. Confidence is high because
the ticket is a precise checklist with explicit out-of-scope boundaries, so the work proceeds
autonomously through the full-proof chain with no human gate.

### Alternatives considered

- Classify as `normal`: rejected — 4 flags fired and the change fans out across every product
  domain's tool contract, so the heavier proof chain (plan + per-task two-stage review) is
  warranted despite each individual edit being mechanical.

### Deviations

- Rule 1 (task 2.2) — Updated pre-existing `test_add_itinerary_item_bad_status_raises` to expect `pydantic.ValidationError` instead of `ToolException`: `status`/`kind` are now enum-validated by `ToolNode` *before* the tool body runs, so the old exception path is unreachable. `apps/api/tests/tools/test_trip_tools.py`. Commit `aaac7f7`.
- Rule 1 (task 2.1) — Fixed pre-existing `test_search_hotels_no_match_returns_message_no_panel`: it forced an empty result with `min_stars=6`, now rejected by the new `min_stars` `le=5` bound. Swapped to `max_price=1` (a valid, unmatchable filter) to preserve the test's intent. Added `test_booking_tools.py` to task 2.1 `<files>`. `apps/api/tests/tools/test_booking_tools.py`.
- Skipped the ticket's explicit `args_schema.model_validate(...)` step — LangChain's `ToolNode` already validates tool-call args against `args_schema` before invoke (confirmed empirically in waves 1–2), so it would be dead code. Intentional, per intake decision.

**Known pre-existing failures (NOT introduced by MIN-46):** `tests/tools/test_routing_tools.py::test_get_city_route_offline_estimate` and `::test_get_route_between_places_offline_estimate` assert the haversine fallback (`source == "estimate"`), but this environment can reach OpenRouteService so `source == "openrouteservice"`. Routing tools are untouched at this point; these are env/network-dependent and out of scope.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| <pending — full tool + registry suite once implemented> | `cd apps/api && make test` | — | intake only; no code changed yet |

### Rollback

- Revert code: `git revert <sha>` (schema-only change, no migration/state)

### Harness-Delta

- Watch: the weakening-validation hook trips on any removed `assert`/`raise` line. Refactors that
  relocate `raise ToolException` guards while adding `args_schema` validation may need
  `RISK_WARN_CATEGORIES="weakening-validation"` at commit — flag if it recurs (→ /compound).
