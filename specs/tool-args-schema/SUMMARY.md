# tool-args-schema — SUMMARY

Lane: normal
Confidence: high

## Change
Every `app/tools` `@tool` now passes an explicit `args_schema=<Tool>Args`. The 16 remaining bare
tools (trip ×9, expense ×3, memory ×3, needs_clarification) get schemas that DECLARE their injected
args (`InjectedState` / `InjectedStore` / `InjectedToolCallId`); the registry guard now requires an
`app.tools.*` schema for every tool.

## Rationale
ToolNode derives injection targets from `args_schema`; only an *omitted* injected field breaks
injection (MIN-46). Declared fields inject correctly and are stripped from `tool_call_schema`
(spiked through a real ToolNode on langchain-core 1.4.8). Function signatures keep their
`Annotated` metadata: the trip guard reads `InjectedState("trip_id")` from type hints and MCP
serves the raw signature.

## Alternatives
- Keep auto-derived schemas for injected tools (status quo) — inconsistent with the rest of the registry.
- Strip descriptions from signatures (flight style) — would degrade the MCP-served schema.

### Verify
| Check | Command | Exit | Notes |
|---|---|---|---|
| Full BE suite | `cd apps/api && ../../.venv/bin/python -m pytest -q` | 0 | 2574 passed |
| Lint | `cd apps/api && ../../.venv/bin/ruff check app/tools tests/tools/test_tool_registry.py` | 0 | clean |

### Rollback
`git revert <sha>`
