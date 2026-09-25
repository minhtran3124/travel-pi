# llm-pricing-coverage — Summary

Lane: normal
Confidence: medium
Reason: no hard gate; 2 flags (existing behavior — observability of cost, weak proof — prices are data); touches >1 file (pricing guard + a script + tests)
Flags: existing-behavior, weak-proof
Affects: app/core/pricing.py, app/agents/metrics.py (cost recording), new apps/api/scripts/ delta script
Input-type: spec slice
Route: using-git-worktrees → subagent-driven-development
Escalate: no

> Documented default (why medium): an unpriced model is surfaced as a WARNING log at graph build / agent_config load plus a unit test asserting every seeded agent_config model has a price row — NOT a dashboard save rejection (that would be a public-contract change → high-risk).
> Prerequisite for `llm-spend-caps`: `estimate_cost` returns `None` for the whole run if ANY model is unpriced (`app/core/pricing.py:53-65`), so a dollar budget summed over `cost_usd` would silently under-count.

### Intent

> make research for
> - https://www.langchain.com/blog/langsmith-llm-gateway-runtime-controls-for-production-agents
> - https://www.langchain.com/langsmith/llm-gateway
> - https://www.langchain.com/blog/how-we-made-coding-agent-spend-predictable
>
> làm 1 nghiên cứu đnahs gía để áp dụng vào project hiện tại

> ok, run /feature-intake cho nhung de xuat o trren

Source backlog: `specs/llm-gateway-eval/research-brief.md` §4 (7 items). This slice covers: items 5 (pricing-miss guard) and 6 (cost-vs-invoice delta script).

## What changed

Intake only — not implemented.

### Rationale

estimate_cost already refuses to fake 0.0; the gap is that the None is silent. A warning + seed-coverage test closes it without changing any contract; the delta script (read-only SUM over agent_runs by month) gives the invoice comparison the LangChain post recommends.

### Alternatives considered

- Reject unpriced models in the config dashboard — deferred: public-contract change.
- Fetch prices from a live API — rejected: no stable official pricing API; adds an external dependency.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |

### Not auto-verified

- Lane/Confidence classification — reached traceability; judged from `research-brief.md` §2 evidence, no diff exists yet.

### Rollback

- `git revert <sha>`

### Harness-Delta

- none
