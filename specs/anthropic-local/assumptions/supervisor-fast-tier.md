# Assumption: Supervisor fast tier

## Context
Supervisor was not in FAST_AGENTS, so with a cold AgentConfigCache or a NULL-model agent_config row it resolved to the main model (sonnet). Adding it to FAST_AGENTS broke about 100 tests, because build_graph.pick also uses FAST_AGENTS to choose the injected test double.

## Decision
Add FAST_MODEL_AGENTS = FAST_AGENTS | {supervisor}, used only for model-tier resolution (get_agent_llm and the seed script). build_graph.pick is unchanged.

## Alternatives
Add supervisor to FAST_AGENTS and rewrite about 100 tests; or leave the supervisor on the main tier and rely on the DB row.

## Impact if wrong
With the OpenAI default and no per-agent row, the supervisor now uses the fast model (gpt-5-mini) instead of gpt-5. This matches the policy of the fast model for classification. If wrong, supervisor routing quality may drop slightly.

## How to reverse
Remove the supervisor from FAST_MODEL_AGENTS, or set a per-agent model in its agent_config row. No data migration needed.
