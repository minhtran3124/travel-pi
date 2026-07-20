# weather-trip-date-accuracy — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator
- date: 2026-07-20
- trigger: hard-gate
- question: How should the agent answer weather questions for dates beyond the forecast horizon — extend the existing tools, or add a distinct climate tool?
- context: MIN-66 / GitHub #97. `get_weather` / `get_packing` are re-exported to MCP clients through `app/mcp/server.py` (wraps `ALL_TOOLS`), so any signature or behavior change is a client-visible contract change → public-contract hard gate, which cannot be self-downgraded.
- options:
  - A) Add an optional `date` / `start_date` to `get_weather` + `get_packing`; internally route to climate normals when the date is beyond the ~16-day forecast horizon. One tool per concept, model cannot pick wrong; but the tool silently changes data source, and the MCP contract shifts for existing clients.
  - B) Keep `get_weather` forecast-only (add the date param, error/caveat beyond horizon) and expose `/destinations/{city}/climate` as a **new separate** `get_climate` tool. Honest separation of forecast vs. normals and additive for MCP; but the model must choose correctly, and picking wrong is exactly the failure class we are fixing.
  - C) Leave both tool signatures untouched; make the prompt refuse to state weather for far-future dates. No contract change at all, ships fastest; but the agent still cannot answer a legitimate question ("what's Tokyo like in September?") that the data already supports.
- default_if_no_response: BLOCK
- decision: **B** — keep `get_weather` forecast-only (add the date param + an explicit
  beyond-horizon signal) and expose `/destinations/{city}/climate` as a new, separate
  `get_climate` tool. Additive for existing MCP clients; forecast vs. climate normals stay
  honestly distinct. Accepted residual risk: the model must pick the right tool, so the
  tool descriptions and the planner/concierge prompt must make the choice unambiguous, and
  a regression case must cover "far-future date → get_climate, never get_weather".
- decided_by: Minh Tran
- decided_at: 2026-07-20
