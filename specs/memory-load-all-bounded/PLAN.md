---
slug: memory-load-all-bounded
status: active
owner: Minh Tran
created: 2026-09-17
---

# Load all instructions and preferences — drop the over-read heuristic

## 1. Motivation

`load_context_node` reads instructions with `limit=20` then `[:10]`, preferences with `limit=16`
then `[:8]`; the `get_user_preferences` tool reads `limit=10` then `[:5]`. The 2× over-read exists
so rows the read guard drops cannot shrink the block below its cap — but the ratio has no
derivation, and the cap itself is redundant since PR #214: new writes are restricted to 6
instruction keys and 13 preference keys, key-addressed, 200 chars each. Only pre-guard legacy rows
can exceed that, and the dev DB holds single digits per user (`SUMMARY.md` → Hard-gate narrowing).

Read everything instead. `limit=50` is a technical ceiling (the store API requires a limit), not a
design cap.

## 2. Non-goals

- No background summarization job.
- No deleting, remapping or rewriting of stored rows (hard gate; removed from scope by the owner).
- Episodes / `recall_past_trips` keep `limit=6` → `[:3]`: unbounded by key, fetched on demand.
- `app/memory/guard.py` and the key allowlists are not touched.

## Global Constraints

- Run every command from the repo root with `.venv/bin/python` / `.venv/bin/ruff`.
- `apps/api/app/memory/guard.py` must not appear in the diff.
- The `recall_past_trips` call `search_episodes(store, user_id, query=query, limit=6)[:3]` stays
  byte-identical.
- The `PROFILE_KEYS` exclusion in `load_context_node` stays; only the `[:8]` slice goes.
- Test-first: write the new test, run it, see it fail on the cap, then change the code.
- Comments: at most one comment line (≤100 chars) per changed call site; docstrings edited or
  added by this plan are ≤2 lines. No added line contains `:param`, `:return`, `limit=20`,
  `limit=16`, `over-read`, or a task number of this plan.
- Stage and commit as separate commands. Commit messages carry no Claude/Anthropic attribution
  trailer of any kind.
- Tests seed legacy rows with raw `store.put` (the write guard would reject non-canonical keys).

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | 12 valid stored instructions produce 12 `- ` lines in the instructions block (today: 10) | `.venv/bin/python -m pytest apps/api/tests/agents/test_load_context_memory_guard.py::test_all_valid_instructions_reach_prompt_without_cap -q` | exit 0 |
| SC-2 | 10 valid + 6 poisoned + 3 profile preferences produce exactly 10 preference lines, none starting `- name:`, none containing `ignore all previous instructions` (today: 8) | `.venv/bin/python -m pytest apps/api/tests/agents/test_load_context_memory_guard.py::test_ten_valid_six_poisoned_three_profile_preferences_all_valid_injected -q` | exit 0 |
| SC-3 | `get_user_preferences` returns 7 items when 7 valid preferences are stored (today: 5) | `.venv/bin/python -m pytest apps/api/tests/tools/test_memory_tools.py::test_get_user_preferences_returns_all_valid_rows -q` | exit 0 |
| SC-4 | No `limit=NN)[:` over-read-then-slice remains for instructions or the preferences tool (the episodes `limit=6)[:3]` is single-digit and deliberately not matched) | `grep -nE "limit=[12][0-9]\)\[:" apps/api/app/agents/nodes.py apps/api/app/tools/memory_tools.py` | exit 1 — no match |
| SC-5 | Episodic recall still returns a valid episode sitting past 3 poisoned ones | `.venv/bin/python -m pytest apps/api/tests/tools/test_memory_tools.py::test_recall_past_trips_valid_episode_past_poisoned_window_survives -q` | exit 0 |
| SC-6 | The three changed modules lint clean | `.venv/bin/ruff check apps/api/app/memory/store.py apps/api/app/agents/nodes.py apps/api/app/tools/memory_tools.py` | exit 0 |
| SC-7 | The preferences block in `load_context_node` is no longer sliced after the `PROFILE_KEYS` exclusion | `grep -n "PROFILE_KEYS\]\[:" apps/api/app/agents/nodes.py` | exit 1 — no match |
| SC-8 | 250 stored instructions are all returned by `get_instructions`, each exactly once, in store order (more than two pages) | `.venv/bin/python -m pytest apps/api/tests/memory/test_search_all.py -q` | exit 0 |
| SC-9 | No `READ_ALL_LIMIT` constant remains anywhere in the app | `grep -rn "READ_ALL_LIMIT" apps/api/app` | exit 1 — no match |
| SC-10 | `load_context_node` passes no `limit=` to any memory read | `grep -n "limit=" apps/api/app/agents/nodes.py` | exit 1 — no match |

## 4. Tasks

### Task 1.1 — load_context reads all instructions and preferences (wave 1)

- **Files:** apps/api/app/memory/store.py, apps/api/app/agents/nodes.py, apps/api/tests/agents/test_load_context_memory_guard.py
- **Action:** In `test_load_context_memory_guard.py`, first add
  `test_all_valid_instructions_reach_prompt_without_cap`: seed 12 instructions via raw
  `store.put` on `_proc_ns(...)` with keys `valid_0..valid_11` and text
  `always confirm option {i} first`; assert the instructions block has exactly 12 non-blank lines.
  Rename `test_ten_valid_six_poisoned_three_profile_preferences_cap_to_eight` to
  `test_ten_valid_six_poisoned_three_profile_preferences_all_valid_injected`, change the count
  assertion from 8 to 10, add an assertion that `ignore all previous instructions` is absent from
  `result["preferences"]`, and replace its docstring and the long ordering comment with one ≤2-line
  docstring naming what it pins (guard drop + profile exclusion, no cap). Run both and confirm they fail on the counts.
  Keep `test_valid_instructions_past_poisoned_window_still_reach_prompt` but replace its
  docstring with ≤2 lines saying poisoned rows ahead of valid ones do not hide them; its body and
  assertions stay byte-identical.
  Then add `READ_ALL_LIMIT = 50` to `store.py` next to `_DEFAULT_SEARCH_LIMITS` with a one-line
  comment (technical ceiling: the store API requires a limit; the write allowlist is the real
  bound). In `nodes.py` import it and change the two reads to
  `get_instructions(store, user_id, limit=READ_ALL_LIMIT)` (no slice) and
  `search_memory_typed(store, user_id, MemoryKind.PREFERENCES, limit=READ_ALL_LIMIT)` with
  `non_profile = [p for p in prefs if p.key not in PROFILE_KEYS]` (no slice). Replace each of the
  two over-read comments with at most one comment line.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/agents/test_load_context_memory_guard.py apps/api/tests/agents/test_preferences_injection.py apps/api/tests/agents/test_procedural_injection.py apps/api/tests/agents/test_profile_injection.py -q`
- **Done:** Verify exits 0; the SC-1 and SC-2 node-id commands exit 0; the SC-7 grep exits 1;
  `grep -c "cap_to_eight" apps/api/tests/agents/test_load_context_memory_guard.py` prints 0.
- **Criteria:** SC-1, SC-2, SC-7
- **Interfaces:** Consumes the existing guarded read helpers in the memory store module (already on main). Produces `READ_ALL_LIMIT` and the updated `apps/api/app/agents/nodes.py`.

### Task 2.1 — get_user_preferences returns all valid rows (wave 2)

- **Files:** apps/api/app/tools/memory_tools.py, apps/api/tests/tools/test_memory_tools.py
- **Action:** In `test_memory_tools.py`, first add
  `test_get_user_preferences_returns_all_valid_rows`: seed 7 preferences via raw `store.put` on
  `("users", "u_pref_all", "prefs")` with keys `valid_0..valid_6`, invoke the tool the way
  `test_get_user_preferences_valid_rows_past_poisoned_window_survive` does, assert `len(result) == 7`.
  Run it and confirm it fails with 5. Then in `memory_tools.py` import `READ_ALL_LIMIT` from
  `app.memory.store` and change the call to
  `search_preferences(store, user_id, query=query, limit=READ_ALL_LIMIT)` (no slice); replace its
  comment with at most one comment line. In `recall_past_trips`, leave the code untouched and make
  its comment self-contained (it currently points at the comment being removed). Replace the
  existing window test's docstring with ≤2 lines; its body and assertions stay byte-identical.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/tools/test_memory_tools.py apps/api/tests/tools/test_tool_registry.py apps/api/tests/agents/test_memory.py -q`
- **Done:** Verify exits 0; the SC-3 and SC-5 node-id commands exit 0; the SC-4 grep exits 1; the
  SC-6 ruff command exits 0; `grep -c "limit=6)\[:3\]" apps/api/app/tools/memory_tools.py` prints 1.
- **Criteria:** SC-3, SC-4, SC-5, SC-6
- **Interfaces:** Consumes `READ_ALL_LIMIT` (Task 1.1). Produces the updated `apps/api/app/tools/memory_tools.py`.

### Task 3.1 — page through the store instead of passing a limit (wave 3)

- **Files:** apps/api/app/memory/store.py, apps/api/app/agents/nodes.py, apps/api/app/tools/memory_tools.py, apps/api/tests/memory/test_search_all.py, apps/api/tests/memory/test_structured_namespaces.py
- **Action:** Owner decision mid-execution: a `limit` at the read sites confuses reviewers — remove
  it. `BaseStore.search` needs an integer `limit`, so read everything by paging. First write
  `tests/memory/test_search_all.py`: seed 250 instructions via raw `store.put` (keys `k000..k249`,
  text `note {i}`) on an in-memory store from `get_store("sqlite:///:memory:")`, assert
  `get_instructions(store, uid)` returns 250 items whose texts equal the seeded list in order; a
  second test does the same for `search_preferences` with 120 rows; a third asserts
  `search_memory_typed(store, uid, MemoryKind.PREFERENCES)` with no limit returns 12 of 12 seeded
  rows and that `MemoryKind.EPISODES` with no limit still returns 3 of 5. Run and confirm they
  fail. Then in `store.py`: add `_PAGE_SIZE = 100` and `_search_all(store, namespace, *, query=None)`
  looping `store.search(..., limit=_PAGE_SIZE, offset=offset)` until a page is shorter than
  `_PAGE_SIZE`; remove the `limit` parameter from `get_instructions` and `search_preferences` and
  have them use `_search_all`; in `search_memory` and `search_memory_typed`, when `limit is None`
  and the kind is not `EPISODES`, use `_search_all`, otherwise keep the existing limited search
  (explicit `limit` still honored; episodes default stays 3); replace `_DEFAULT_SEARCH_LIMITS` with
  `_EPISODE_DEFAULT_LIMIT = 3`; delete `READ_ALL_LIMIT`. In `nodes.py` and `memory_tools.py` drop
  the `READ_ALL_LIMIT` import and the `limit=` argument at the three call sites. In
  `test_structured_namespaces.py` replace `test_search_memory_default_limits_per_kind` with a test
  of the same name asserting `_EPISODE_DEFAULT_LIMIT == 3`.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/memory apps/api/tests/agents/test_load_context_memory_guard.py apps/api/tests/tools/test_memory_tools.py -q`
- **Done:** Verify exits 0; the SC-8 command exits 0; the SC-9 and SC-10 greps exit 1; the SC-1,
  SC-2, SC-3, SC-5 node-id commands exit 0; the SC-6 ruff command exits 0;
  `grep -c "limit=" apps/api/app/tools/memory_tools.py` prints 1.
- **Criteria:** SC-8, SC-9, SC-10
- **Interfaces:** Consumes `READ_ALL_LIMIT` call sites (Tasks 1.1, 2.1). Produces `_search_all` in `apps/api/app/memory/store.py`.

## 5. Risks

- **Unbounded legacy rows** (revised with Task 3.1): nothing falls off any more, so a user with
  very many pre-guard rows gets a proportionally long prompt block. Production counts are
  `unknown` (never queried); dev max is 4 instructions / 5 preferences per user.
- **Pagination loop** ends on the first page shorter than `_PAGE_SIZE`; a store that ignores
  `offset` and always returns a full page would not terminate. Both langgraph stores honor it.
- **Prompt size:** worst case for allowlisted rows is ≈300 tokens (instructions) + ≈500 tokens
  (preferences) per turn; legacy rows add to that until someone cleans them, which this spec does
  not do.
- **Tool result shape:** `get_user_preferences` can now return more than 5 items to the model.
  Same fields, longer list.
- **Harness binding:** `specs/gh-193-booking-revise-idempotency/PLAN.md` is also `status: active`
  and sorts first, so `blast-radius-check.sh` will warn on every file here against the wrong plan.
  Expected noise, not a scope signal.

## 6. Status Log

- 2026-09-17 — intake (normal / high), hard gate narrowed by owner (cleanup script removed). Plan written.
- 2026-09-17 — independent plan review: approved with changes. Applied: SC-4/SC-6 mapped to Task 2.1 only
  (not satisfiable after wave 1); `Done` restated as exit codes; comment/docstring instructions made
  countable. Not applied (advisory): anchoring SC-4 on `READ_ALL_LIMIT` — a generic `limit=X)[:` pattern
  would also match the in-scope-untouched episodes line; SC-1/2/3 already fail on any reintroduced cap.
- 2026-09-17 — task 1.1 complete; commits 9d1c623f, e4b3f604 (review: spec pass / quality approved, 3 Minor — 2 fixed, 1 resolved).
- 2026-09-17 — task 2.1 complete; commit f5a738f9 (review: spec pass / quality approved, 2 Minor recorded).
- 2026-09-17 — owner, mid final-review: remove `limit` from the read sites entirely ("gây confuse cho ng review").
  `BaseStore.search` requires an int limit, so owner chose pagination. Six in-flight FIND reviewers stopped
  (stale diff). Added Task 3.1 + SC-8..SC-10; `READ_ALL_LIMIT` is superseded.
- 2026-09-17 — task 3.1 complete; commit 42ff7ae3 (review: spec pass / quality approved, 2 Minor — fixed in ed5b1937).
- 2026-09-17 — correctness review: 6/6 angles found a paging hang on queried reads; fixed ed5b1937, re-review "fix holds";
  follow-up latent finding fixed 3969416f. Three advisories recorded in SUMMARY.md.

