# UAT — agent-run-trace-detail (per-step call chain + detail page)

**Date:** 2026-09-03 · **Branch:** `feat/agent-run-trace-detail` (off `feat/agent-turn-metrics`)
**Stack:** real — docker Postgres with the `AsyncPostgresSaver` checkpointer, a genuine Supabase
ES256 token, real OpenAI. Every number in the screenshot came from an agent turn.

## What the screenshot shows

`agent-run-detail.png` is `/dashboard/agent-runs/{id}` for a real multi-intent stream turn
(7 LLM calls, 40,247 in / 741 out / 18,304 cached, $0.0239, 13,727 ms).

| Evidence | Where |
|---|---|
| The **parallel fan-out is visible**: steps 5 and 6 are two `synthesis_worker` nodes starting at the same offset with different durations (2,461 ms and 5,260 ms) | call chain rows 5–6 |
| Sub-graph nodes are attributed and indented (`assistant in synthesis_worker`) | rows 7–21 |
| A **real tool failure** was captured, not staged: `resolve_date` → `error · ToolException`, 842 ms | row 18 and the Tools table |
| Two models blended in one turn, both dated snapshots priced through `normalize_model` | Cost by model |
| Prompt links carry `?version=` so they open the version that ran | Prompt versions table |

## Verified behaviour

- **Single-intent turns attribute per-step prompts correctly**: `concierge:<uuid>|assistant:<uuid>`
  resolves to `concierge v11 + communication_style v8`; `supervisor` → v9; `reflection` → v1.
- **Multi-intent turns cannot**: the live namespace is
  `synthesis_worker:<uuid>|assistant:<uuid>` — the specialist name appears nowhere in it, so those
  steps carry no prompt pointer. The design's first draft claimed the specialist sat in the middle
  namespace segment; **that was wrong and the code comment now says so**, verified against a live
  turn. The run-level snapshot still records every active version.
- The prompts table is therefore labelled "Prompt versions active for this run" with an explicit
  "attributed to a step" column, rather than claiming every listed prompt was used.

## Findings from running it for real

- **A repository-level `create_all` pre-created the new table on Postgres**, so
  `alembic upgrade head` failed with `DuplicateTable`. Four repositories call
  `Base.metadata.create_all` on *any* backend, not just SQLite. This is the "schema ownership
  split" item from the 2026-09-02 deep review, now demonstrated: boot the app before running
  migrations and the migration breaks. Not caused by this branch; recorded as a follow-up.

## Not covered

Prompt attribution on the multi-intent path (needs `state["task"]` plumbed to the callback);
retention for the step rows; content-level debugging, which the intake decision deliberately
excludes.
