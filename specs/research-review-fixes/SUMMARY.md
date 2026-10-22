# research-review-fixes — Summary

Lane: normal
Confidence: high
Reason: fixes inside the research feature that PR #221 adds; no migration, no change to existing
public contracts, chat product untouched.
Flags: none
Affects: apps/api research runner + router; apps/web Research tab, chat plan panel, research watch hook
Input-type: change request

### Intent

> run /compound-engineering:ce-code-review for current PR.

Then the owner's decisions on the review's open items (decision page:
https://claude.ai/artifact/CHp1TeQ5twSYNHYAVzEHVV): D1 deferred (#225), D2 A, D3 B, D4 A, D5 A,
D6 deferred (#226), D7 A.

## What changed

Applied during the review (verified findings):
- Revise now forwards `language` and `origin`. Before this, a Vietnamese dossier switched to English on revise.
- A cancelled run is no longer finalised as `completed`.
- The SSE snapshot loop ends with an `interrupted` error for a `running` row that has no live bus channel.
- Clicking Apply again skips entries that already applied, so items are no longer duplicated.
- The day map in the chat panel memoises its markers and route, so MapLibre is not rebuilt on every render.
- The Research tab refetches the latest summary when the live stream settles.
- 503 responses get the `ServiceUnavailable` label.

Owner decisions:
- **D3.** On `CancelledError` the runner leaves the row `running`, publishes `interrupted` and closes the channel. The next start resumes it from the checkpoint without spending the daily cap. `bus.has()` is False after close, so a start in the same process also resumes.
- **D5.** `_status_body` shows a `running` row with no live channel as `interrupted`. This is display only; the DB is not written.
- **D2.** `proposal_ready` is true only for a completed run. The Research tab shows a "didn't finish" card with a "Run again" button, and hides Apply for a failed or interrupted run. The dossier stays readable.
- **D4.** `useResearchWatch` exposes `updating` while a newer run is running. The chat plan panel then disables Apply and shows "Updating…".

Tests added: PUT files (owner round-trip and 404 for another user's run), `chat_state` for live and not-live runs, cancellation, resume after cancel, orphan status, `proposal_ready` on a failed run, revise forwarding, and the frontend unfinished, updating and double-Apply cases.

### Rationale

D3-B reuses the orphan-resume path that is already tested, instead of adding a new `interrupted` → fresh-turn
path that would cost the traveller a daily-cap slot for a server reload. D5 keeps the status read-only so the
resume path still works. D2/D4 block the one harmful action (Apply writes into the real trip) without changing
the per-trip storage design.

### Alternatives

- D3-A: finalise as `interrupted`. Rejected because it spends the traveller's cap and does not resume.
- D4-B: snapshot the proposal per run. Deferred; too large for this PR.
- D5-B: a periodic sweep. Rejected because sweeping flips rows to `interrupted`, which breaks resume.

### Verify

| Check | Command | Exit | Notes |
|---|---|---|---|
| BE research | `cd apps/api && DATABASE_URL=sqlite:///$(mktemp -d)/t.db OPENAI_API_KEY= ../../.venv/bin/python -m pytest tests/research tests/api/research -q` | 0 | 140 passed, 2 skipped |
| BE full (clean worktree, no .env) | `cd apps/api && DATABASE_URL=sqlite:///$(mktemp -d)/t.db OPENAI_API_KEY= ../../.venv/bin/python -m pytest -q` | 1 | 3044 passed, 9 skipped; 1 failure `test_llm_defaults_require_no_key` fails identically on HEAD 8f126fe7 without these changes |
| BE lint | `cd apps/api && ../../.venv/bin/ruff check app && ../../.venv/bin/ruff format --check app/research/runner.py app/routers/research.py` | 0 | |
| FE tests | `cd apps/web && pnpm vitest run` | 0 | 64 files, 425 passed |
| FE types + lint | `cd apps/web && pnpm tsc --noEmit && pnpm lint` | 0 | 1 pre-existing warning (useAgentStream.ts) |

### Rollback

`git revert 097f4bed`
