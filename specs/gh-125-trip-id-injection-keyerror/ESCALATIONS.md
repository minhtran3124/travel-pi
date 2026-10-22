# gh-125-trip-id-injection-keyerror — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator (surfaced by the correctness-review guard-completeness/prior-art finder)
- date: 2026-08-28
- trigger: in-flight
- question: Accept that `trip_id` is no longer a required field on the MCP tool schema for the five trip tools, or neutralize it?
- context: The fix is implemented, reviewed and green (commits `a5c48ca`, `3616338`), but it changes a public contract that neither `design.md` nor `PLAN.md` reasoned about. `app/mcp/server.py` builds each tool's MCP `inputSchema` from the raw function signature via `inspect.signature`, not from `tool_call_schema`. Giving `trip_id` a default to satisfy LangGraph's optional-injected-state tolerance therefore also moved it out of `required` on the MCP surface. Verified by building the server against both revisions:
    - base `76a68ae` — `get_trip_summary` required `['trip_id', 'user_id']`; `add_place_to_trip` required `['place_id', 'trip_id', 'user_id']`
    - HEAD — `get_trip_summary` required `['user_id']`; `add_place_to_trip` required `['place_id', 'user_id']`
  Consequence: an MCP client may now omit `trip_id`. Previously FastMCP rejected such a call before the tool body ran; now it succeeds and returns the `_no_active_trip()` guidance, whose wording ("this conversation", "ask the traveller") is written for a chat sub-agent and reads oddly for a programmatic caller.
- options:
  - A) Accept as-is, record the contract delta in `SUMMARY.md`, and add an MCP-schema assertion to the regression tests so the change is pinned rather than incidental. Relaxing `required` is backward compatible — every call that was valid before stays valid — and the new reachable state returns a structured `error: no_active_trip` rather than a crash. Cost: the guidance wording stays chat-flavoured for MCP callers.
  - B) Accept, and additionally reword `_no_active_trip()` to be caller-neutral (state that no trip was supplied, keep the create_trip pointer) so it reads correctly for both the agent and an MCP client. Cost: one more source commit, which invalidates the current review receipt and needs the affected review re-run.
  - C) Keep `trip_id` required on the MCP surface by diverging the two surfaces — e.g. filtering or re-annotating in `app/mcp/server.py`. Cost: real machinery in the MCP layer for a bug fix, and `server.py` is outside this plan's declared Files set.
- recommendation: B — the contract relaxation itself is benign and worth keeping, but the wording is cheap to fix now and is the only part that actually reads wrong. A is acceptable if you would rather not spend another review round.
- default_if_no_response: BLOCK
- decision: B — accept the relaxed MCP contract, pin it with an MCP-schema assertion in the regression tests, and reword `_no_active_trip()` to be caller-neutral
- decided_by: Minh Tran
- decided_at: 2026-08-28
