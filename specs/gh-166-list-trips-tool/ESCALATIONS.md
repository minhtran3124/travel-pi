# gh-166-list-trips-tool — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator (feature-intake)
- date: 2026-09-09
- trigger: ambiguous-direction
- question: Does this fix ship read-only `list_trips` alone, or also a trip-resolution/`select_trip` step so the agent can act on a non-active trip by name?
- context: Issue #166 suggestion 3 leaves this open. It decides the whole scope: option A is one read-only tool; option B additionally mutates `TravelAgentState.trip_id` mid-conversation, which changes what every other trip tool operates on.
- options:
  - A) `list_trips` only (read-only) + prompt guard + eval goldens. Answers "how many trips do I have" correctly and lets the model name the others. "Tell me about my Da Nang trip" still cannot pull that trip's details — the agent would have to say which trip is active. Smallest blast radius, no state mutation.
  - B) A + a trip-resolution step (`select_trip`, or a `trip_id` argument on the read tools) so a trip named in conversation becomes the target. Fully closes the issue's Expected section, but rebinds the active trip inside a turn — every `trip_id`-injected tool changes meaning, and the FE's notion of the active trip can drift from the agent's.
- default_if_no_response: BLOCK
- decision: A — `list_trips` only (read-only) + prompt guard + eval goldens. No `select_trip`, no
  mid-turn rebinding of `TravelAgentState.trip_id`. "Tell me about my <other trip>" is answered by
  naming the trips and saying which one is active; pulling a non-active trip's details is OUT OF
  SCOPE for this fix and stays open on #166.
- decided_by: minhtran3124
- decided_at: 2026-09-09

## E002

- raised_by: orchestrator (feature-intake)
- date: 2026-09-09
- trigger: hard-gate
- question: Authorize the `public-contract` hard gate — a new agent tool is auto-exposed over `/agent/manifest` and MCP; confirm `list_trips` should be reachable by MCP clients, or must it be filtered out of the MCP surface?
- context: `ALL_TOOLS` in `apps/api/app/tools/registry.py` is what the MCP server and the manifest publish, so registration alone ships the contract. Prior art: spec `review-a-security-hardening` had to filter destructive tools explicitly in `server.py` because `InjectedState` does NOT remove a tool from MCP.
- options:
  - A) Expose over MCP (read-only, `user_id` from `InjectedState`). Matches agent-native parity and the issue's Notes; requires proving the MCP path cannot be called with an attacker-chosen `user_id`.
  - B) Register for the sub-agents but filter `list_trips` out of the MCP server surface. Narrower blast radius, breaks parity for MCP clients.
- default_if_no_response: BLOCK
- decision: A — expose over MCP (read-only, `user_id` from `InjectedState`), for agent-native
  parity. Condition of the authorization: the plan MUST carry a test proving the MCP path cannot
  be called with a caller-supplied `user_id` (i.e. `user_id` is not in the published input schema
  and cannot be overridden), since `InjectedState` alone does not remove or protect a tool on the
  MCP surface.
- decided_by: minhtran3124
- decided_at: 2026-09-09
- superseded_by: E003 — the condition attached to this decision turned out to be unsatisfiable
  (`user_id` IS caller-supplied over MCP). E003 replaces this with option B: not exposed over MCP.

## E003

- raised_by: agent (brainstorming, step 1 inspection)
- date: 2026-09-09
- trigger: hard-gate
- question: E002-A's condition is unsatisfiable as written — over MCP, `user_id` IS a caller-supplied argument. Expose `list_trips` anyway (accepting the exposure), exclude it from MCP, or fix the class first?
- context: Blocks `design.md`. Evidence (re-runnable): `build_mcp_server()` serves `tool.func`, and FastMCP derives the input schema from the RAW signature, so the `InjectedState` annotation is invisible to it. `get_trip_summary`'s served `inputSchema` today lists `user_id` as a plain optional string (verified by dumping it). The MCP surface is unauthenticated — `app/mcp/server.py` runs standalone (`python -m app.mcp.server`, not mounted in `main.py`), and `specs/review-a-security-hardening` E004 already excluded destructive tools for exactly this reason. Existing read tools share the flaw but also require guessing a trip UUID; `list_trips` needs only a `user_id`, turning a UUID-guessing problem into a one-argument inventory dump — an enumeration primitive that does not exist on the MCP surface today.
- options:
  - A) Expose anyway, drop the unmeetable condition, document the residual risk. Only defensible if the MCP server is treated as trusted/local single-user. Adds the first user_id-only data-harvest tool to an unauthenticated surface.
  - B) Register for the sub-agents, exclude `list_trips` from MCP by name in `server.py` (the existing destructive-exclusion precedent) + a test asserting it is absent. Fixes #166 fully on the agent path; MCP parity is deferred, not silently broken.
  - C) Fix the class first: stop serving caller-supplied `user_id` over MCP at all (bind a process identity, or strip injected params from the served schema). The real fix, but it touches every trip tool and is its own spec — out of scope for #166.
- recommendation: B now, C as a follow-up issue. B keeps #166's actual bug (the wrong trip count in chat) fully fixed and does not widen an unauthenticated surface on the way.
- default_if_no_response: BLOCK
- decision: B — register `list_trips` for the sub-agents; exclude it from the MCP surface by name
  in `app/mcp/server.py` (alongside the destructive exclusion), with a test asserting it is absent
  from `list_tools()`. Supersedes E002-A. Open a follow-up issue for option C (stop serving
  caller-supplied `user_id` over MCP for every trip tool) — out of scope for #166.
- decided_by: minhtran3124
- decided_at: 2026-09-09
