# UAT — agent-turn-metrics (per-turn token / cost / latency)

**Date:** 2026-09-03 · **Branch:** `feat/agent-turn-metrics` @ `cb55db6` (PR #131)
**Base:** `main @ 1aee549`. **CI (Postgres):** api pass 11m35s · web pass 1m45s (run 33719713916).

## Result: 19 / 19 PASS (12 offline + 7 against the live stack)

| # | Test case | Result | Evidence |
|---|---|---|---|
| TC01 | A `/agent/chat` turn returns per-turn usage and leaves one `agent_runs` row `completed`/`turn` with `by_node` containing `supervisor` | PASS | `results.json` |
| TC02 | A graph failure still returns the fallback reply (200) and records the row `failed` — metrics never break the answer | PASS | `results.json` |
| TC03 | A HITL plan-approval interrupt records `interrupted`; the resume turn opens a second row `kind=resume` | PASS | `results.json`, `dashboard-agent-runs.png` |
| TC04 | A `/agent/stream` turn records `completed` with `channel=stream` and the `done` event carries `usage` | PASS | `results.json`, `dashboard-agent-runs.png` |
| TC05 | If the `agent_runs` insert fails, the user still gets their reply | PASS | `results.json` |
| TC06 | A crashed or cancelled stream turn still persists a real latency (fix) | PASS | `results.json`, `dashboard-agent-runs.png` |
| TC07 | Uncaptured usage reports cost as UNKNOWN, not a confident $0.0000; one unpriced model poisons the total to `None` (fix) | PASS | `results.json`, `dashboard-agent-runs.png` |
| TC08 | A retried graph node is timed again while a nested run sharing the namespace stays deduped (fix) | PASS | `results.json` |
| TC09 | OpenAI models are built asking for `usage_metadata`; other SDK profiles are untouched | PASS | `results.json` |
| TC10 | `/dashboard/agent-runs` renders for an operator in dev and is hidden (404) in production | PASS | `dashboard-agent-runs.png` + live guard check below |
| TC11 | The `agent_runs` migration applies and rolls back cleanly (additive) | PASS | `results.json` |
| TC12 | Background memory extraction reports into `background_*` columns without touching the turn totals | PASS | `results.json` |

### Live-stack cases (real Supabase login, real OpenAI spend, real Postgres)

| # | Test case | Result |
|---|---|---|
| LIVE-01 | A real `/agent/chat` turn returns usage and records a `completed` row (`b4c77b78`: 5 calls, 27,195 in / 25,600 cached, **$0.0037**, 6268 ms, flow `concierge`) | PASS |
| LIVE-02 | A real multi-intent `/agent/stream` turn fans out and converges; `done` carries usage (`bc6d5259`: flow `synthesize`, 9 calls, 52,322 in / 49,152 cached, **$0.0083**, 6881 ms) | PASS |
| LIVE-03 | A real failing turn still records latency and cost (`6e2e2282`: `failed`, 1 LLM error, **$0.0175**, 6460 ms) | PASS |
| LIVE-04 | The Alembic revision applies to real Postgres, creating the table and its three indexes | PASS |
| LIVE-05 | A real dated-snapshot model name (`gpt-5.4-mini-2026-03-17`) resolves to a price | PASS |
| LIVE-06 | `/agent/*` rejects an unauthenticated call (401) | PASS |
| LIVE-07 | After gpt-5 access was granted, the previously-403 multi-intent turn completes and its cost is blended across **two** models, both dated snapshots (`0d4ce5e9`: 9 calls, **$0.0266**, 14,272 ms) | PASS |

**Total measured cost of this UAT: $0.0588 across 7 real turns** — measured by the feature itself.


Machine-readable: `results.json` (each case lists the exact test node-ids behind it).

## Method

Two layers, because this feature has both a behavioural and a visual surface.

**Behaviour (TC01–TC12).** Each case runs the real shipped code through its actual test node-ids
with a scripted `FakeLLM` — deterministic, offline, zero LLM spend. Runner: session scratchpad
`uat_run.py` (not checked in). Every credential is set to the empty string rather than unset,
because an *unset* variable lets `apps/api/.env` supply the developer's real key while a *set*
one overrides it.

**Pixels + live stack.** `dashboard-agent-runs.png` is the **real page showing real traffic**: a
local uvicorn against the docker Postgres (`AsyncPostgresSaver` checkpointer, not the degraded
MemorySaver), authenticated with a genuine Supabase ES256 access token, driving real turns through
the real OpenAI account. Captured with Node 24 `@playwright/test` chromium at 1440x950,
deviceScaleFactor 2. Every number in the screenshot was produced by the agent, not seeded.

## What the screenshot proves

Every row is a real turn, and the screenshot happens to capture this branch's own before/after:

- **`6e2e2282` (Failed, $0.0175, 6460 ms).** A genuine provider error (the account has no access
  to `gpt-5`, which an unconfigured node falls back to). Before the final-review fix this row
  would have carried NULL latency and NULL cost and dropped out of the rollups entirely. It is the
  strongest evidence in this UAT: the failure was not staged.
- **`40ab5197` (Running) and `889576dc` (Abandoned).** Two real chat turns that answered the user
  correctly but left their row stuck at `running`. That is the durability bug this UAT found (see
  below); the two `completed` chat rows above them were run after the fix.
- **`bc6d5259` (synthesize, 9 calls, 49,152 cached).** The multi-intent fan-out converging on one
  synthesized answer — the shape shipped in PR #130 — now with its cost attached.

Cached-token accounting is working against the real provider: 49,152 of 52,322 input tokens were
served from cache on that turn. That number is what makes the deferred prompt-caching spec
measurable, which was the point of doing this one first.

The clearest demonstration of why this feature exists is the top two rows. `0d4ce5e9` and
`bc6d5259` are the *same* multi-intent request, same flow, same nine LLM calls — and they cost
**$0.0266 and $0.0083**, a 3.2x spread. The only difference is which model answered the
`synthesize` node: the first fell back to `gpt-5`, the second to `gpt-5.4-mini`. The per-model
breakdown makes the cause legible — one `gpt-5` call producing 637 output tokens outweighs eight
`gpt-5.4-mini` calls consuming 42,900 input tokens:

```
0d4ce5e9 by_model:
  gpt-5-2025-08-07          1 call    232 in  /   637 out  /      0 cached
  gpt-5.4-mini-2026-03-17   8 calls  42,900 in /   356 out  / 20,480 cached
```

Both names carry a dated snapshot suffix, so both had to pass through `normalize_model` before the
price table could resolve them. Per-node timing on the same turn: `synthesize` 6,749 ms,
`reflection` 2,418 ms, `supervisor` 961 ms, `load_context` 8 ms.

## Live guard check (TC10)

Same database, same route, no dashboard credentials configured:

```
development  /dashboard/agent-runs -> 200
production   /dashboard/agent-runs -> 404
production   /dashboard/bookings   -> 404
```

The new page inherits the router-level `require_dashboard_access` dependency from PR #129, so it
hides in production exactly like every other dashboard page.

## What this UAT found — a regression this branch introduced, now root-caused

Running for real caught a defect no offline test could: **`/agent/chat` answered correctly but its
`agent_runs` row stayed `running` forever, and the assistant reply was never saved.**

An earlier draft of this document blamed a pre-existing bug in `get_session`. **That was wrong.**
A controlled experiment settled it: running the chat handler with `main`'s exact background-task
shape (no `run_id` / `session_factory`) persists everything correctly — row `completed`, messages
`user,assistant`. The regression belongs to this branch.

### Root cause: an application-level deadlock on the run row

Instrumenting `get_session` showed its teardown never executed for a failing turn — only
`CREATE`, then nothing, with no exception. `pg_stat_activity` during a failing run shows why:

| Connection | State | Query |
|---|---|---|
| request session | `idle in transaction`, waiting on `ClientRead` | `UPDATE agent_runs SET status=…` |
| background task | `active`, waiting on `Lock` / `transactionid` | `UPDATE agent_runs SET background_llm_calls=…` |

The cycle:

1. The handler flushes `finish()` onto the request-scoped session. Flush, not commit — so the
   transaction stays open and **holds a row lock** on that `agent_runs` row.
2. The handler returns. FastAPI runs the registered background task, which is where this branch
   newly asked `run_memory_extraction` to write `background_*` columns **on the same row**,
   through a second connection. It blocks on the row lock.
3. The dependency teardown that would `COMMIT` and release the lock is only reached after the
   background task finishes. It never finishes.

Postgres cannot break this: neither side is waiting on the *database* in a way that forms a
detectable cycle, so it simply waits forever. Every failing turn also leaked one
`idle in transaction` connection.

### Why the fix is right

Committing the post-graph writes explicitly before the handler returns releases the row lock
*before* the background task runs. Verified on the live stack after the fix: row `completed`,
`background_llm_calls=1 / background_tokens=1341 / background_ms=1426` (the write that used to
deadlock), messages `user,assistant`, and zero lock waits or idle-in-transaction connections.

A regression test pins the invariant with a deliberately non-committing session override
(`test_run_row_is_durable_without_the_request_session_commit`); it fails without the fix.

Real data also exposed a layout defect the seeded run had hidden: with genuine 36-character UUID
run and user ids the table overflowed and clipped the latency column. Both ids are now truncated
to eight characters with the full value in a `title` attribute.

### The general lesson

A background task must not write a row that the request session has flushed but not committed.
Either commit before returning, or do not touch the same row from a background task.

## Not covered here

Two environment issues surfaced that belong to the project, not to this branch, and were left
alone:

- The multi-intent `synthesize` / `synthesis_worker` nodes have no `agent_config` row, so they
  fall back to the env default. That first produced a 403 (the account lacked `gpt-5`); after
  access was granted the turn completes, but it silently routes the most expensive node to the
  most expensive model — a 3.2x cost difference for the same request. Seeding an `agent_config`
  row for those nodes is the real fix, and the dashboard is now what makes the case for it.
- `get_session` itself is sound; no other handler needs changing. The pattern to avoid is
  narrower than first thought: a background task writing a row the request session has flushed
  but not committed.

Cost accuracy against live provider billing is still unverified: the dashboard shows this
implementation's estimate from the static price table, not what OpenAI actually invoices.
