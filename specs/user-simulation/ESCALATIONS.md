# user-simulation — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator (feature-intake)
- date: 2026-09-25
- trigger: hard-gate
- question: Should virtual users reach the chatbot over real HTTP/SSE (JWT per persona) or in-process through evalkit's LangGraphRunner?
- context: decides whether the auth hard gate stays in scope, and how realistic the simulation is
- options:
  - A) HTTP `/agent/stream` with one test user + JWT per persona. Most realistic: rate limiter, SSE, persistence. Touches auth (token minting for test users).
  - B) In-process LangGraphRunner (like eval). No auth or HTTP, reuses DbOracle, but skips the router, SSE, and rate-limit layers.
  - C) B first, A later as a second slice.
- default_if_no_response: BLOCK
- decision: A) HTTP /agent/stream with a test user + JWT per persona, from v1 (auth gate stays in scope)
- decided_by: Minh Tran
- decided_at: 2026-09-25

## E002

- raised_by: orchestrator (feature-intake)
- date: 2026-09-25
- trigger: ambiguous-direction
- question: Where does the 2D simulation UI live?
- context: decides FE scope, dependencies, and whether it ships to users
- options:
  - A) A dev-only page in apps/web (e.g. /dev/simulation), hidden in production.
  - B) A standalone tool (single HTML/canvas file or a small app under tools/), no product surface.
  - C) A published Artifact page that replays transcripts from JSON.
- default_if_no_response: BLOCK
- decision: B) standalone tool (single HTML/canvas or a small app under tools/), no product surface
- decided_by: Minh Tran
- decided_at: 2026-09-25

## E003

- raised_by: orchestrator (feature-intake)
- date: 2026-09-25
- trigger: ambiguous-direction
- question: Should the UI show sessions live or replay saved transcripts?
- context: live needs a push channel (SSE/WebSocket) from the simulator to the UI; replay only needs transcript files
- options:
  - A) Replay only (v1): the simulator writes transcript JSON; the UI animates it.
  - B) Live: the UI subscribes while the simulation runs.
  - C) Replay in v1, live in v2.
- default_if_no_response: BLOCK
- decision: B) live from v1: the UI subscribes while the simulation runs
- decided_by: Minh Tran
- decided_at: 2026-09-25

## E004

- raised_by: orchestrator (feature-intake)
- date: 2026-09-25
- trigger: ambiguous-direction
- question: How are the virtual users driven on the Claude Code quota?
- context: decides whether a run is an interactive Claude Code session or a scriptable batch
- options:
  - A) A `claude -p` script (from a clean directory, `--output-format json`, `--json-schema`): batchable, cron/Makefile-friendly.
  - B) Claude Code subagents / Workflow inside an interactive session: no script, but a run needs an open session.
  - C) A, plus a thin skill or command that launches it from a session.
- default_if_no_response: BLOCK
- decision: C) a `claude -p` batch script plus a thin skill that launches it from a session
- decided_by: Minh Tran
- decided_at: 2026-09-25
