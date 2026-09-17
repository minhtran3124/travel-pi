# memory-load-all-bounded — Summary

Lane: normal
Confidence: high
Reason: two flags, no hard gate after the owner narrowed scope — `existing-behavior` (the read caps on instructions/preferences go away) and `audit/security`-adjacent (the memory read path, guard untouched). The only hard-gated item (a script deleting legacy store rows → `data-loss/migration`) was removed from scope by the owner at intake.
Flags: existing-behavior, audit/security
Affects: apps/api/app/agents/nodes.py (`load_context_node`), apps/api/app/tools/memory_tools.py (`get_user_preferences`)
Input-type: change request
Route: writing-plans (PLAN.md — >2 files) → using-git-worktrees → subagent-driven-development
Escalate: no — hard gate narrowed by the owner on 2026-09-17 (see `### Hard-gate narrowing`)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

Asked about `instrs = get_instructions(store, user_id, limit=20)[:10]`:

> giải thích vì sao chỉ limit=20

> vì sao ko lấy hêts?

> ko hợp lý lắm, nên load hết instructions của user là 1
> chúng ta có thể làm 1 background job summary nếu instructions vượt ngưỡng chúng ta đề ra

After PR #214 merged, the assistant sketched a design — load everything (technical ceiling
`limit=50`, no cap), no background summarization job because PR #214's write allowlist already
bounds the set, a one-off legacy-row cleanup script, and a test pinning the bound. The owner
answered:

> có

Then, asked how to narrow the hard-gated cleanup script:

> Bỏ script khỏi scope (Recommended)

Mid-execution (tasks 1.1 and 2.1 done, final review running), on seeing `limit=READ_ALL_LIMIT`:

> nếu thực sự bỏ cap 20 thì nên remove cái limit này luôn, đừng đưa vào code, gây confuse cho ng review.

The assistant reported that `BaseStore.search` requires an integer `limit` (default 10; `None`
crashes), so "no limit" is only reachable by paginating, and offered two implementations. The
owner chose:

> Phân trang đọc hết (Recommended)

### Hard-gate narrowing

| Question | Decision | Consequence |
| --- | --- | --- |
| The legacy-row delete/remap script trips `data-loss/migration`. Keep it? | **Removed from scope** (owner, 2026-09-17) | No store row is deleted or rewritten by this spec. Legacy rows keep surfacing through the read guard exactly as today. |

Evidence behind the decision (dev DB, read-only query on `store`, 2026-09-17): 5 `procedural`
rows, all 5 with non-canonical keys (`timed_itinerary`, `travel_pace`, `dont_ask`, `trip_style`,
`budget_band`), max 4 per user; 14 `prefs` rows, 1 non-canonical (`trip_pace`), max 5 per user.
Production was not queried — `unknown`.

### Scope

**In scope**

- `load_context_node`: read all instructions and all preferences, no post-guard cap.
  `PROFILE_KEYS` exclusion stays.
- `get_user_preferences` tool: same, no `[:5]` cap.
- **Revised 2026-09-17 (owner, mid-execution):** no `limit` at any of these call sites. The store
  helpers page through `store.search` with `offset` until a short page, so nothing is capped and
  nothing can fall off silently. Supersedes the first cut's `READ_ALL_LIMIT = 50`.
- Tests: replace the over-read/cap assertions with the bound that now does the work — what is
  injected is limited by the write allowlist, not by a read window.

**Out of scope**

- Any background summarization job (the owner's original idea; superseded — see Rationale).
- Deleting/remapping legacy rows (hard gate, removed above).
- Episodes / `recall_past_trips` — unbounded by key, fetched on demand via semantic search;
  their growth is a TTL question, P1 of `specs/agent-memory-layer-5`.
- The instruction allowlist itself. Noted, not acted on: all 5 real dev instructions use keys
  outside the 6 canonical ones, and `dont_ask` / `timed_itinerary` map to none of them.

## What changed

`load_context_node` and the `get_user_preferences` tool now read every stored instruction /
preference instead of over-reading a 2× window and slicing to 10 / 8 / 5 — and the call sites pass
no `limit` at all. `BaseStore.search` has no unlimited mode, so `app/memory/store.py` pages through
it (`_read_all`: offset paging, rows told apart by namespace + key, stops on a short page or a page
with nothing new). A read that carries a semantic `query` is a top-k search and is never paged — it
uses the store's own default limit. Episodes are untouched (`recall_past_trips` keeps 6 → 3;
default recall stays 3). The read guard and the `PROFILE_KEYS` exclusion are unchanged.

### Rationale

The `limit=20 → [:10]` over-read is a heuristic guarding a cap that PR #214 made redundant: new
instruction writes are restricted to 6 canonical keys, key-addressed (overwrite), 200 chars each —
so ≤6 rows ≈ 300 tokens per user; preferences ≤10 non-profile keys ≈ 500 tokens. Only pre-guard
legacy rows can exceed that, and the dev DB shows single digits. Reading everything removes the
"how much over-read is enough" question instead of tuning it.

### Alternatives considered

- **Background summarization job above a threshold** (the owner's proposal) — not needed for
  instructions/preferences once the allowlist bounds them, and it would add an LLM call that reads
  stored memory: a new re-injection point that would itself need the guard.
- **Keep over-read, pin the 2× ratio with a test** — keeps a heuristic with no derivation.
- **One-off legacy cleanup script** — removed by the owner; hard-gated and not needed for the bound.

### Deviations

- none (no Rule 1–3 auto-fix by either implementer).

### Review findings (per-task, all Minor — none blocking)

- 1.1 — deleted comment lost the reason `search_memory_typed` is used over `search_preferences`
  → **fixed** in `e4b3f604` (one comment line).
- 1.1 — new test asserted a count only → **fixed** in `e4b3f604` (asserts the 12 lines by content and order).
- 1.1 — reviewer could not confirm the window test's body was byte-identical (review package
  truncated) → **resolved** by the controller with `git diff 40a6d98d..9d1c623f`: docstring-only.
- 2.1 — controller caught, before commit, an added docstring containing `over-reading` (Global
  Constraint) and two `§3.4` citations pointing at the removed cap → **fixed** in `f5a738f9`.
  The implementer's own forbidden-token scan had reported clean.
- 2.1 — "Read all rows" comments sit next to a ceiling of 50; the nuance lives at the constant's
  definition → **recorded**, not changed.
- 2.1 — test-first ordering is attested only by the implementer reports (`assert 10 == 12`,
  `assert 8 == 10`, `assert 5 == 7`), not observable in the tree → **recorded**.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| baseline before change (intake) | `.venv/bin/python -m pytest apps/api/tests/agents/test_load_context_memory_guard.py apps/api/tests/tools/test_memory_tools.py -q` | 0 | 19 passed on `baf46eea` (main with #214), run from repo root | |
| SC-1 12 instructions reach the prompt | `.venv/bin/python -m pytest apps/api/tests/agents/test_load_context_memory_guard.py::test_all_valid_instructions_reach_prompt_without_cap -q` | 0 | at 3969416f | SC-1 |
| SC-2 10 valid preferences, no poison/profile | `.venv/bin/python -m pytest apps/api/tests/agents/test_load_context_memory_guard.py::test_ten_valid_six_poisoned_three_profile_preferences_all_valid_injected -q` | 0 | at 3969416f | SC-2 |
| SC-3 tool returns all 7 | `.venv/bin/python -m pytest apps/api/tests/tools/test_memory_tools.py::test_get_user_preferences_returns_all_valid_rows -q` | 0 | at 3969416f | SC-3 |
| SC-4 no `limit=NN)[:` left | `grep -nE "limit=[12][0-9]\)\[:" apps/api/app/agents/nodes.py apps/api/app/tools/memory_tools.py` | 1 | exit 1 = no match (expected) | SC-4 |
| SC-5 episodic recall unchanged | `.venv/bin/python -m pytest apps/api/tests/tools/test_memory_tools.py::test_recall_past_trips_valid_episode_past_poisoned_window_survives -q` | 0 | at 3969416f | SC-5 |
| SC-6 lint | `.venv/bin/ruff check apps/api/app/memory/store.py apps/api/app/agents/nodes.py apps/api/app/tools/memory_tools.py` | 0 | at 3969416f | SC-6 |
| SC-7 preferences not sliced | `grep -n "PROFILE_KEYS\]\[:" apps/api/app/agents/nodes.py` | 1 | exit 1 = no match (expected) | SC-7 |
| SC-8 paged read returns every row once | `.venv/bin/python -m pytest apps/api/tests/memory/test_search_all.py -q` | 0 | 6 tests at 3969416f, incl. the hang reproduction | SC-8 |
| SC-9 no `READ_ALL_LIMIT` | `grep -rn "READ_ALL_LIMIT" apps/api/app` | 1 | exit 1 = no match (expected) | SC-9 |
| SC-10 no `limit=` in load_context | `grep -n "limit=" apps/api/app/agents/nodes.py` | 1 | exit 1 = no match (expected) | SC-10 |

### Not auto-verified

- Production legacy-row counts were never queried. With pagination nothing falls off, but a user
  with very many legacy rows would get a proportionally long prompt block; dev max is 4 / 5.
- Pagination against `PostgresStore` was not executed — tests run on `InMemoryStore`. Reached
  provenance only: langgraph 1.2.6 `postgres/base.py` emits `LIMIT %s OFFSET %s` from
  `op.limit` / `op.offset` for both the plain and the vector query.

### Rollback

- `git revert <sha>` — read-path only, no data written or deleted.

### Correctness review (final gate) — BASE baf46eea

Six FIND angles ran on `42ff7ae3`; all six reported the same defect and four reproduced it by
execution. The controller reproduced it too (the new regression test was killed by SIGALRM after
20 s on `42ff7ae3`). Independent SCORE dispatch was skipped for that location: it was fixed
regardless of score, so threshold routing was moot. An adversarial re-review of the fix
(`ed5b1937`) returned **fix holds**, with boundaries executed at 0/1/99/100/101/199/200/201 rows.

| Finding | Severity | Outcome |
| --- | --- | --- |
| Queried read through the paging loop never terminated / returned duplicates on `InMemoryStore` (langgraph ignores `offset` for unembedded rows) | P0–P1 | **fixed** `ed5b1937` — a queried read is never paged; unqueried paging dedupes and stops on a page with nothing new |
| Queried read on `PostgresStore` silently capped at ~201 candidates while claiming "every row" | P2 | **fixed** `ed5b1937` — queried reads are top-k by contract; docstrings say so |
| `get_user_preferences(query=…)` returned all rows merely re-ranked | P2 | **fixed** `ed5b1937` — queried reads return the store's top matches (≤10; was ≤5 before this branch) |
| Dedupe keyed on `key` only, but `store.search` matches a namespace prefix | P3 latent | **fixed** `3969416f` — keyed on `(namespace, key)`, with a test |
| Legacy (pre-allowlist) rows are no longer capped in the prompt or the tool result | P2, Rule 4 | **advisory — owner decision**, see `### Intent` and PLAN §5; comment wording corrected (the allowlist bounds new writes only) |
| Unqueried multi-page read is not atomic: a write landing between pages can skip a boundary row; ≥100 concurrent inserts could end the read early | P3 | **advisory** — only reachable above 100 rows in one user namespace (dev max: 5); duplicates are removed by the dedupe |
| Tool wording "Optional free-text filter" / "Matching saved preferences" overstates a top-k search | P3 | **advisory** — pre-existing (top-k always filled before this branch too); model-facing text left unchanged |
| Task 3.1 per-task review, 2 Minor (test name overstated; missing return annotations) | Minor | **fixed** `ed5b1937` |

### Harness-Delta

- backlog — `review_package.py` truncated the 1.1 package mid-hunk (248 lines), forcing a
  `cannot_verify` the controller had to settle by hand. → `compound`.
- backlog — an implementer's self-run "forbidden token" scan reported clean while an added line
  contained `over-reading`; countable constraints should be checked by the controller, not
  self-attested. → `compound`.
- backlog — `correctness-reviewer-prompt.md` documents fragment paths without the `.claude/` prefix;
  `render_skill_prompt.py` exits 1 on them in a consumer install. → `compound`.
- backlog — `run_state.py` has no transition out of `verifying` back to implementation, so an
  owner scope change during the final gate leaves the durable state stale. → `compound`.
- backlog — teammate results are truncated in delivery (~4–5 findings lost per report) and
  read-only reviewers cannot write a report file; every FIND result needed a follow-up message. → `compound`.
