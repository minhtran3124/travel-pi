# User simulation

A batch of LLM-driven "travellers" chat with the Travel Planner agent on an isolated,
throwaway stack (`api-sim` on `:8001`, `db-sim` on `:5434`), so you can exercise the chatbot
end-to-end and mine transcripts for golden test candidates. Each traveller is a `claude -p`
process; the chatbot under test runs on OpenAI.

## Prerequisites

- Docker running.
- `apps/api/.env` with a real `OPENAI_API_KEY` (the chatbot runs on OpenAI).
- Claude Code logged in with a subscription (see the terms note below).

## Setup

Bring the sim stack up (build + start, wait for `/healthz`). Run from the repo root:

```bash
make sim-up
```

`make sim-down` stops the stack (keeps the volume); `make sim-reset` also removes the volume.

## Run a batch

```bash
make sim-run N=8 PARALLEL=3            # N travellers, PARALLEL at a time
make sim-run N=8 PARALLEL=3 PERSONAS=<file> SEED=<n>   # optional overrides
```

Watch it live in the UI at <http://localhost:8765/>.

## Outputs

Each batch writes to `apps/api/sim/runs/<UTC-timestamp>/` (gitignored):

- `personas.json` — the travellers for this batch
- `transcript.jsonl` — every turn
- `report.json` / `report.md` — per-persona pass/warn/fail grades
- `candidates/golden_candidates.json` — mined golden test candidates

## Quota guard

Traveller processes spend shared Claude plan quota, so the orchestrator is self-throttling: a new
traveller is admitted only while both the 5-hour and 7-day utilization stay below
`SIM_QUOTA_CEILING` (default `0.85`). Lower it to leave more headroom; raise it to push closer to
the limit.

## Environment

- `SIM_CLAUDE_MODEL` — model for the traveller processes (default `sonnet`).
- `SIM_QUOTA_CEILING` — utilization ceiling for admitting new travellers (default `0.85`).
- `SIM_CLAUDE_BIN` — path to the `claude` binary (tests point this at a fake).

## Terms note (2026-09-25)

As of 2026-09-25 the Agent SDK credit change is paused, so `claude -p` draws from the shared
Claude plan's 5-hour and weekly limits. The simulator never passes `--bare`: `--bare` would bill
`ANTHROPIC_API_KEY` instead of the subscription. Keep batches small so a run does not exhaust the
plan quota.
