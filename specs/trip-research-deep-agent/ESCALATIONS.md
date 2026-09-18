# trip-research-deep-agent — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator
- date: 2026-09-18
- trigger: hard-gate
- question: Where does the dossier live?
- context: Decides whether a migration hard gate is added and how the FE reads/edits files.
- options:
  - A) deepagents `StoreBackend` on the existing LangGraph Postgres store, namespace `("users", user_id, "research", trip_id)` — no migration, files are the unit the agent edits with `edit_file`, FE reads via a small `GET .../research/files` route. (recommended)
  - B) Own table `trip_research_docs` — SQL-queryable and joinable to trips, but adds a migration (data-loss/migration gate) and a second write path the agent tools must mirror.
- default_if_no_response: BLOCK
- decision: A — StoreBackend on the existing Postgres store, namespace (users, user_id, research, trip_id); no migration.
- decided_by: Minh Tran (owner)
- decided_at: 2026-09-18

## E002

- raised_by: orchestrator
- date: 2026-09-18
- trigger: ambiguous-direction
- question: How does the job run and how does the user follow it?
- context: Decides the API contract and whether a worker process is introduced.
- options:
  - A) FastAPI `BackgroundTask` after `POST /trips/{id}/research` returns 202 with a run id; progress persisted in `agent_runs`/`agent_run_steps`; FE polls `GET .../research/{run_id}`. Same pattern as memory extraction; dies with the process (acceptable for v1). (recommended)
  - B) SSE stream of the run like `/agent/stream` — live progress, but a minutes-long stream and the FE stream contract (lockstep with `apps/web/src/lib/stream/`) both grow.
  - C) Separate worker process/queue — survives restarts, but new infrastructure (Docker service, queue) for a mock backend.
- default_if_no_response: BLOCK
- decision: A+B — BackgroundTask job persisted in agent_runs/agent_run_steps with a poll endpoint AND an SSE progress stream in v1 (trip page + chat both consume it); chat entry only starts the job and points at the progress. Option C (worker/queue) rejected.
- decided_by: Minh Tran (owner)
- decided_at: 2026-09-18

## E003

- raised_by: orchestrator
- date: 2026-09-18
- trigger: ambiguous-direction
- question: Which entry surface ships first?
- context: Decides whether the supervisor prompt/graph is touched in this feature.
- options:
  - A) REST route + a "Research this trip" action on the trip page only; chat stays untouched. (recommended — keeps the "do not touch the 5 specialists / supervisor" boundary)
  - B) Also route "research my trip" from chat: new supervisor target + suggestion chip; touches supervisor prompt v14 and `route_tasks`.
- default_if_no_response: BLOCK
- decision: B — both surfaces: REST + trip-page action AND a chat entry (new supervisor target, prompt v14, route_tasks, suggestion chip). The 'do not touch supervisor' boundary from the assessment is lifted for the routing hop only; the 5 specialists stay untouched.
- decided_by: Minh Tran (owner)
- decided_at: 2026-09-18

## E004

- raised_by: orchestrator
- date: 2026-09-18
- trigger: hard-gate
- question: May the job write to the real trip?
- context: Writes (itinerary items, shortlist) are user data; decides whether HITL plumbing is built into a background job.
- options:
  - A) Propose-only v1: the dossier contains a machine-readable proposal (`/plan/proposal.json`); the user applies it from the trip page through existing REST endpoints. No write tool bound to the job. (recommended)
  - B) Job binds `add_itinerary_item` / `add_place_to_trip` with `interrupt_on`; the FE resumes the run after approval — needs interrupt/resume for background runs and a new approval UI.
- default_if_no_response: BLOCK
- decision: A — propose-only v1: dossier carries /plan/proposal.json; user applies via existing REST from the trip page; no write tool bound to the job.
- decided_by: Minh Tran (owner)
- decided_at: 2026-09-18
