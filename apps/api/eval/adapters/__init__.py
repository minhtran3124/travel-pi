"""travel-pi binding layer for evalkit — the only place that imports `app.*`.

`evalkit/` (the portable core) never depends on this repo; adapters here
implement its ports (`AgentRunner`, `Oracle`, ...) against the real agent
graph, DB, and services. See `specs/agent-eval-pipeline/design-portability.md`.
"""
