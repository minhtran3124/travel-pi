---
problem_type: bug
module: agent/tools
tags: langgraph, tool-node, injected-state, injected-store, args-schema, tool-design, dependency-injection
severity: critical
applicable_when: Adding or reviewing a LangGraph `@tool` that takes runtime-injected args (`InjectedState`/`InjectedStore`) and deciding whether to hand-author an explicit `@tool(args_schema=...)`.
affects:
  - apps/api/app/tools/memory_tools.py
  - apps/api/app/tools/hotel_tools.py
  - apps/api/app/tools/flight_tools.py
  - apps/api/app/tools/registry.py
supersedes: null
confidence: high
confirmed_at: 2026-07-16
---

## Applicable When

You are writing or reviewing a LangGraph `@tool` that receives runtime-injected arguments
(`InjectedState`, `InjectedStore`) and you are tempted to give it a hand-authored
`@tool(args_schema=MyArgs)` — e.g. to control the model-facing field descriptions.

## Context

`ToolNode` derives *which arguments to inject* from the tool's schema, not just from the
function signature. So an explicit `@tool(args_schema=MyArgs)` that lists only the model-facing
fields and **omits** the injected params hides those injected fields from `ToolNode` as well as
from the LLM. `ToolNode` then calls the tool without them.

Symptom:

```
TypeError: <tool>() missing 2 required positional arguments: 'user_id' and 'store'
```

This bit the memory tools first (`save_user_preference` / `get_user_preferences` /
`recall_past_trips`, MIN-46). It recurred as a live concern when MIN-65 added an injected
`preferences` arg to the hotel/flight search tools — those correctly keep the injected field
on the schema (see "How to Apply") rather than omitting it.

## How to Apply

Two working shapes, one broken:

- ✅ **Auto-derived schema (preferred for injection-only tools).** Do NOT hand-author an
  `args_schema`. Keep it auto-derived from the signature and attach model-facing descriptions
  inline:

  ```python
  def get_user_preferences(
      key: Annotated[str, Field(description="Preference key to look up.")],
      user_id: Annotated[str, InjectedState("user_id")],
      store: Annotated[BaseStore, InjectedStore()],
  ) -> str: ...
  ```

  The auto-derived `tool_call_schema` already strips injected args from what the model sees.

- ✅ **Explicit schema that KEEPS the injected field.** If a tool must have a hand-authored
  `args_schema` (MIN-65's search tools do, for the rich model-facing filter descriptions),
  declare the injected field *on the schema too*, annotated with `InjectedState`:

  ```python
  class SearchHotelsArgs(AppBaseModel):
      city: str = Field(..., description="...")
      preferences: Annotated[str, InjectedState("preferences")] = Field(
          default="", description="Injected — never supplied by the model."
      )
  ```

  `ToolNode` sees the injection target on the schema; the model-facing `tool_call_schema` still
  strips it. Declaring it on **both** the schema and the function signature is correct, not
  redundant.

- ❌ **Explicit schema that OMITS the injected field.** Breaks injection → the `TypeError` above.

## Testing Gotcha

Schema-only unit tests (asserting `.args` / `tool_call_schema`) do **not** catch this — only an
integration path through `ToolNode` does (e.g. `tests/agents/test_planner_episodic.py`). Also
`tool.get_input_schema().model_json_schema()` raises `PydanticInvalidForJsonSchema` on `BaseStore`
for these tools — assert against `tool.tool_call_schema.model_fields` instead.

## Enforcement

The `ALL_TOOLS` guard in `tests/tools/test_tool_registry.py` exempts injection-bearing tools
(requiring every model-facing field to be described) while requiring a hand-authored
`app.tools.*` schema for all others.

Shipped under MIN-46 (`specs/standardize-tool-args-schema/`, commit `278c0fc`); reconfirmed
by the MIN-65 preference-injection tools (PR #89). Related:
[[llm-parses-code-computes]], [[side-panel-language-decisions]].
