# flight-fare-no-fabrication — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator
- date: 2026-07-20
- trigger: hard-gate
- question: May the fix change the `search_flights` tool contract to add `return_date`, or should it stay prompt/summary-only?
- context: MIN-67 / GitHub #98. `search_flights` is re-exported to MCP clients through `app/mcp/server.py` (wraps `ALL_TOOLS`), so a new parameter is a client-visible contract change → public-contract hard gate, which cannot be self-downgraded.
- options:
  - A) Wire `return_date` through the tool (service and REST endpoint already support it), label the fare one-way + currency in the summary, and tighten the planner guardrail against derived prices. Agent can genuinely answer round-trip questions; MCP contract gains one optional param.
  - B) No tool change — summary labelling + prompt guardrail only. Zero contract risk, but the agent can only ever refuse a round-trip question, never answer it.
- default_if_no_response: BLOCK
- decision: **A** — wire `return_date` through the tool, label one-way + currency in the summary,
  and tighten the planner guardrail so a price may never be arithmetically derived. The parameter
  is optional, so existing MCP clients are unaffected. Accepted trade: one added optional field on
  a client-visible contract, in exchange for the agent being able to answer the question correctly
  instead of either lying or refusing.
- decided_by: Minh Tran
- decided_at: 2026-07-20
