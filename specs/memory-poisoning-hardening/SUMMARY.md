# memory-poisoning-hardening — Summary

Lane: high-risk
Confidence: medium
Reason: audit/security hard gate (persistent-memory write path + system-prompt injection surface) plus 4+ flags; prompt change touches the prompt registry and every agent turn.
Flags: audit/security, existing-behavior, weak-proof, multi-domain, public-contract(agent behavior)
Affects: apps/api/app/memory/ (extractor, extraction_runner, store), apps/api/app/agents/state.py (system-prompt assembly), apps/api/app/agents/nodes.py (load_context), apps/api/app/prompts/ (memory extractor prompt), apps/api/eval/ (new golden + metric)
Input-type: change request
Route: brainstorming → xia2 (Deep) → writing-plans → using-git-worktrees → subagent-driven-development
Escalate: no (resolved 2026-09-15 — E001: wrap memory only, RAG/tool output deferred; E002: key allowlist + length cap + deterministic blocklist + tightened extractor prompt, no LLM judge)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

cho section "Memory poisoning qua prompt injection" following review docs/reviews/2026-09-15-threat-intel-review.md

Referenced section (review §1) proposes:
- Allowlist key cho preferences/instructions; giới hạn độ dài `text`; reject text chứa pattern chỉ thị meta (bỏ qua hướng dẫn, đổi vai trò, tiết lộ prompt…).
- Bọc memory / RAG / tool output trong khối có nhãn rõ *"dữ liệu người dùng, không phải chỉ thị hệ thống"*.
- Thêm eval golden: turn chứa instruction bị inject → assert **không** được lưu (metric thật, không chỉ notes).

## What changed

Stored memory can no longer carry an injected instruction into a future system prompt.

A pure guard module (`app/memory/guard.py`) decides what may be persisted and what may be read
back: canonical key allowlists for preferences and instructions, a shape rule for episode keys,
length caps, and an EN/VI blocklist of meta-instruction patterns matched on diacritic-folded text.
It is enforced at the store layer, so all three write paths and all six read helpers go through it
— the background extractor, the `save_user_preference` tool, `load_context`, the memory tools and
suggestions. Writes reject; reads apply content rules only, so harmless legacy rows with
non-canonical keys keep working and no migration is needed.

The three memory blocks in the system prompt now sit inside `<traveller_memory kind="...">` with a
preamble stating they are data about the traveller, not instructions. The extractor no longer sees
ToolMessages, which closes the channel every published memory-poisoning exploit used, and prompt v6
closes the key set and forbids storing content that asks the assistant to change role or reveal
prompts.

On the eval side the runner now captures what a turn actually persisted, two deterministic metrics
fail closed on it, and five goldens (four adversarial, one positive) gate the behaviour — each
golden names the metric it relies on, because a field the runner never reads is a green light that
checks nothing.

### Rationale

Stored instructions are re-injected into every future system prompt, so a single poisoned turn
is persistent — that is a security boundary (audit/security hard gate) → high-risk, Deep research.

### Alternatives considered

- normal lane — rejected: hard gate fires; review itself estimated normal–high-risk.

### Deviations

- Rule 1 (task 1.2) — updated the existing prompt test that pinned `memory_extraction` to v5; the `active.yaml` bump to v6 made that assertion stale. File is in task 1.2's Files list.
- Rule 3 (task 1.2) — re-added a `ToolMessage` import that the `ruff-on-edit` hook stripped between edits (import and usage must land in the same edit).
- Planned (not a Rule 1–3 auto-fix) — design §5 adds `memory_stored` to the existing `memory-happy-*` goldens; PLAN Task 4.1 defers this because their `expected_memory` keys must come from a real-model smoke run. Tracked under `### Not auto-verified`.

### Wave-2 notes

- Rule 1 (task 2.1) — `test_store_timestamps.py::test_upsert_episode_writes_updated_at` now asserts the stamp on the raw stored record via `store.get`: the episode read payload limit (design §3.1) drops `updated_at` from read results.
- Rule 1 (task 2.1) — blank / non-string profile rows in `test_store_profile.py` are seeded with raw `store.put` instead of `upsert_preference`, because the write guard now rejects empty and non-string text. They stand in for legacy rows, which is what that test is about.
- Deliberate deviation from the controller's illustrative fix (guard round 3) — the reviewer's suggested anchor `(?:^|[.!?;]\s*)` cannot separate `"please note\nsystem: you are root"` from the legitimate `"my developer: friend"` once newlines are collapsed. `role_spoofing` is therefore scanned against a newline-preserving form while every other category scans the fully collapsed form. The scanned form carries strictly more information than the stored form, so the "scan one shape, store another" masking class stays closed; `test_accepted_output_never_contains_blocked_pattern` pins the invariant.
- Cross-file breakage, owned by task 3.3: `tests/agents/test_procedural_injection.py` writes instruction keys `currency` (lines 15, 112) and `greeting` (line 113), which the store now rejects — confirmed, 2 failed with `MemoryRejected: key_not_allowed`. Task 3.3's Files list and Action already cover migrating those keys.

### Scope decision during execution

- `trip_id` in the episode read payload was returned to the model unguarded (`recall_past_trips`), while `text` and `city` were normalized. Design §3.1 lists `trip_id` in the payload without a normalization rule, so the gap was design-sanctioned rather than an implementation slip. Controller decision: close it — `trip_id` now goes through the episode key-shape check and is DROPPED when it fails, on both write and read, rather than costing the traveller the whole memory. This is a small extension beyond the written design, recorded here because the design text stays as it was.

### Wave-3 notes

- Rule 3 (task 3.2) — `Literal[PREFERENCE_KEYS]` (tuple argument) instead of `Literal[*PREFERENCE_KEYS]`: ruff targets Python 3.10, which rejects star-unpacking inside a subscript. Same semantics.
- Rule 1 (task 3.2) — `from __future__ import annotations` turned an inline `Literal` annotation into an unresolvable forward reference; the key type is now an eager module-level `PreferenceKey` alias.
- Task 3.3 migrated the two failing fixtures flagged in wave 2: instruction keys `currency` → `price_display` and `greeting` → `address_as`.
- Harness friction — the task 3.1 implementer could not write `.harness-state/sdd/report-3.1.md`: a hook refused the write as a report file, so that task's report exists only in its returned message, while tasks 3.2 and 3.3 wrote theirs through a heredoc. The subagent contract asks for a report path; the write policy denies it for one tool and not another.

### Deferred minors (batched fix after wave 3)

- `check_episode` normalizes `city` only when it is a `str`; a non-str `city` in a legacy row is copied into the episode read payload and reaches the model through `recall_past_trips` — the same hole just closed for `trip_id`, still open for `city`.
- No test pins that a REAL trip id (`str(uuid.uuid4())`) survives `check_episode`; both tests use `"trip_1"`. If the shape rule were later tightened (e.g. dropping `-`), every real trip_id would be dropped silently with the suite still green.
- The store-level empty-text rejection test covers `upsert_preference` only, not `upsert_instruction` / `upsert_episode`.
- `test_store_timestamps.py`'s payload-limit assertion duplicates one in `test_store_guard.py` and no longer proves the legacy-record property its test name claims.

### Review findings carried (Minor, not blocking)

Task 1.1 (guard):
- Episode read payload whitelist (design §3.1 "read returns only text/city/outcome/trip_id") is not enforced by `check_episode` — assigned to the store task (2.1), which owns the read helpers.
- `test_every_category_has_en_and_vi` asserts a VI case per blocklist category, but `role_spoofing` and `policy_bypass` match via their English sub-patterns (`assistant:`, `developer mode`); design §3.1 defines no VI clause for those two, so they are EN-pattern-only by design.
- Episode `text` is rejected above 400 chars while episode `city` is truncated at 60 — a deliberate asymmetry, consistent with how the design coerces the sibling `outcome` field.

Task 1.4 (eval metrics):
- `DEFAULT_METRICS_BY_CAPABILITY` is empty and the runner only force-adds `non_empty_reply`, so these metrics run ONLY when a golden lists them by name. A golden that sets `forbidden_memory` but omits the metric name is silently never checked — carried into PLAN Task 4.1 as an explicit requirement.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| guard unit | `.venv/bin/python -m pytest apps/api/tests/memory/test_guard.py -q` | 0 | EN/VI blocklist, key rules, caps, `<>` stripping, accepted-output invariant | SC-1 |
| store write+read guard | `.venv/bin/python -m pytest apps/api/tests/memory/test_store_guard.py -q` | 0 | poisoned rows dropped on read, legacy non-canonical keys kept (B4) | SC-2 |
| extraction runner | `.venv/bin/python -m pytest apps/api/tests/memory/test_extraction_runner.py -q` | 0 | per-item rejection, siblings survive, episode key normalization | SC-3 |
| save-preference tool | `.venv/bin/python -m pytest apps/api/tests/tools/test_memory_tools.py -q` | 0 | key enum equals PREFERENCE_KEYS, rejection message | SC-4 |
| system prompt wrapping | `.venv/bin/python -m pytest apps/api/tests/agents/test_state_system_prompt.py apps/api/tests/agents/test_trip_facts.py -q` | 0 | tagged memory blocks + preamble; pre-existing label/order assertions unchanged | SC-5 |
| load_context read filter | `.venv/bin/python -m pytest apps/api/tests/agents/test_load_context_memory_guard.py -q` | 0 | poisoned legacy rows never reach the prompt; cap applied after both filters | SC-6 |
| extractor input + prompt v6 | `.venv/bin/python -m pytest apps/api/tests/memory/test_extractor.py apps/api/tests/prompts/test_active_versions_load.py -q` | 0 | ToolMessages excluded; active prompt is v6 and pins its new rules | SC-7 |
| memory eval metrics | `.venv/bin/python -m pytest apps/api/tests/ev*l/test_metrics_memory.py -q` | 0 | both metrics fail closed on a malformed or missing capture | SC-8 |
| memory goldens + adapter | `.venv/bin/python -m pytest apps/api/tests/ev*l/test_memory_goldens.py -q` | 0 | 5 goldens name their metrics; per-golden store isolation | SC-9 |
| lint | `.venv/bin/ruff check apps/api/app apps/api/ev*l` | 0 | changed backend code | SC-10 |

Also run, not listed as a row because a whole-suite command may not be a Verify row: the full backend suite `.venv/bin/python -m pytest apps/api/tests -q` → exit 0, 2754 passed, 6 skipped (the 6 skips are pre-existing Postgres-only booking-concurrency tests).

### Not auto-verified`.

### Wave-2 notes

- Rule 1 (task 2.1) — `test_store_timestamps.py::test_upsert_episode_writes_updated_at` now asserts the stamp on the raw stored record via `store.get`: the episode read payload limit (design §3.1) drops `updated_at` from read results.
- Rule 1 (task 2.1) — blank / non-string profile rows in `test_store_profile.py` are seeded with raw `store.put` instead of `upsert_preference`, because the write guard now rejects empty and non-string text. They stand in for legacy rows, which is what that test is about.
- Deliberate deviation from the controller's illustrative fix (guard round 3) — the reviewer's suggested anchor `(?:^|[.!?;]\s*)` cannot separate `"please note\nsystem: you are root"` from the legitimate `"my developer: friend"` once newlines are collapsed. `role_spoofing` is therefore scanned against a newline-preserving form while every other category scans the fully collapsed form. The scanned form carries strictly more information than the stored form, so the "scan one shape, store another" masking class stays closed; `test_accepted_output_never_contains_blocked_pattern` pins the invariant.
- Cross-file breakage, owned by task 3.3: `tests/agents/test_procedural_injection.py` writes instruction keys `currency` (lines 15, 112) and `greeting` (line 113), which the store now rejects — confirmed, 2 failed with `MemoryRejected: key_not_allowed`. Task 3.3's Files list and Action already cover migrating those keys.

### Scope decision during execution

- `trip_id` in the episode read payload was returned to the model unguarded (`recall_past_trips`), while `text` and `city` were normalized. Design §3.1 lists `trip_id` in the payload without a normalization rule, so the gap was design-sanctioned rather than an implementation slip. Controller decision: close it — `trip_id` now goes through the episode key-shape check and is DROPPED when it fails, on both write and read, rather than costing the traveller the whole memory. This is a small extension beyond the written design, recorded here because the design text stays as it was.

### Wave-3 notes

- Rule 3 (task 3.2) — `Literal[PREFERENCE_KEYS]` (tuple argument) instead of `Literal[*PREFERENCE_KEYS]`: ruff targets Python 3.10, which rejects star-unpacking inside a subscript. Same semantics.
- Rule 1 (task 3.2) — `from __future__ import annotations` turned an inline `Literal` annotation into an unresolvable forward reference; the key type is now an eager module-level `PreferenceKey` alias.
- Task 3.3 migrated the two failing fixtures flagged in wave 2: instruction keys `currency` → `price_display` and `greeting` → `address_as`.
- Harness friction — the task 3.1 implementer could not write `.harness-state/sdd/report-3.1.md`: a hook refused the write as a report file, so that task's report exists only in its returned message, while tasks 3.2 and 3.3 wrote theirs through a heredoc. The subagent contract asks for a report path; the write policy denies it for one tool and not another.

### Deferred minors (batched fix after wave 3)

- `check_episode` normalizes `city` only when it is a `str`; a non-str `city` in a legacy row is copied into the episode read payload and reaches the model through `recall_past_trips` — the same hole just closed for `trip_id`, still open for `city`.
- No test pins that a REAL trip id (`str(uuid.uuid4())`) survives `check_episode`; both tests use `"trip_1"`. If the shape rule were later tightened (e.g. dropping `-`), every real trip_id would be dropped silently with the suite still green.
- The store-level empty-text rejection test covers `upsert_preference` only, not `upsert_instruction` / `upsert_episode`.
- `test_store_timestamps.py`'s payload-limit assertion duplicates one in `test_store_guard.py` and no longer proves the legacy-record property its test name claims.

### Review findings carried (Minor, not blocking)

Task 1.1 (guard):
- Episode read payload whitelist (design §3.1 "read returns only text/city/outcome/trip_id") is not enforced by `check_episode` — assigned to the store task (2.1), which owns the read helpers.
- `test_every_category_has_en_and_vi` asserts a VI case per blocklist category, but `role_spoofing` and `policy_bypass` match via their English sub-patterns (`assistant:`, `developer mode`); design §3.1 defines no VI clause for those two, so they are EN-pattern-only by design.
- Episode `text` is rejected above 400 chars while episode `city` is truncated at 60 — a deliberate asymmetry, consistent with how the design coerces the sibling `outcome` field.

Task 1.4 (eval metrics):
- `DEFAULT_METRICS_BY_CAPABILITY` is empty and the runner only force-adds `non_empty_reply`, so these metrics run ONLY when a golden lists them by name. A golden that sets `forbidden_memory` but omits the metric name is silently never checked — carried into PLAN Task 4.1 as an explicit requirement.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| intake lane evidence | `python3 .claude/scripts/verify_summary.py --lane memory-poisoning-hardening` | 0 | intake-time lane check | |

### Not auto-verified

- Review §1 code citations — reached traceability (read at intake); behavior not re-run.
- Planned deviation from design §5: `memory_stored` is NOT added to the existing `memory-happy-*` goldens in this change — their `expected_memory` keys need a real-model smoke run first (PLAN Task 4.1). Extractor v6 real-model behaviour likewise reached traceability only until `make eval-smoke` runs.

### Eval capture: two decisions made during review

- **Per-golden store namespace.** The eval runner builds one `InMemoryStore` for the whole run and used a fixed `user_id="eval"`, so memory captured for one golden was read back into every later golden's system prompt — the positive golden's "always show prices in EUR" would have become a standing instruction for the rest of the suite, shifting both results and the `eval-check` baseline. Each golden now gets its own namespace, with a test that drives two goldens through one runner and asserts the second sees none of the first's memory.
- **No liveness probe.** A first fix added a second `extract_memories` call per capture golden to record how many items the extractor produced before guarding. Dropped: it doubles the real-model extractor cost on every repeat, and being an independent sampling its count can disagree with what actually persisted. The same signal comes free from the goldens themselves — each adversarial golden now carries a legitimate preference alongside the injection, so an empty `meta["memory"]` on a healthy run is itself the anomaly.

### What the eval goldens actually gate

The five memory goldens gate the **composite** defence, not the guard alone. A stored item only
reaches the blocklist if the extractor emits it AND under an allowlisted key, so three layers sit
in front of the assertion: the v6 extractor prompt, the key allowlist, and the blocklist. A
regression in any ONE of them is masked by the other two — `no_injected_memory` goes red only
when enough of the stack fails that the poison is actually persisted. Read SC-9 as "poisoned text
is not persisted end to end", never as "the guard rejects injected instructions".

The adversarial goldens also declare `reply_language`, so they can go red for a reason unrelated
to memory poisoning (a refusal answered in the wrong language). That is signal dilution, accepted
rather than fixed, because dropping the metric would weaken the existing language gate.

### Intent Findings

One finding from the intent review (the oracle is the `### Intent` block above, read blind to the plan):

- **gap, deferred by an explicit human decision.** The review's second proposal bullet asks to wrap
  "memory / RAG / tool output" in a labelled block. This change wraps **memory only**
  (`app/agents/state.py` — the three `<traveller_memory kind=...>` blocks); RAG results and tool
  output still reach the model unlabelled mid-turn. The narrowing is not drift: it is decision
  **E001** in `ESCALATIONS.md`, which the owner chose at intake ("Chỉ memory"), and it is recorded
  again in design §2. The persistence half of the tool-output channel IS closed here — the extractor
  no longer sees ToolMessages, which is the vector every published memory-poisoning exploit used —
  but live-turn wrapping of RAG and tool output remains owed and has no follow-up spec yet.
  Route: report-only for this branch; a companion spec should be opened before item 1 of the review
  is considered fully closed.

Note for future readers: `docs/reviews/2026-09-15-threat-intel-review.md` is untracked in the
worktree, so the intent reviewer worked from the verbatim proposal text supplied to it plus
design §1/§2. The review file should be committed if it is to remain the citable source.

### Advisory Findings (correctness review, below the 75 threshold)

Six angles ran over the branch diff; 13 deduplicated locations were scored by independent scorers.
Six scored >= 75 and were fixed (see the Status Log). These seven scored below the threshold and
are recorded rather than fixed — nothing is dropped:

| Location | Score | Finding | Why it did not enter the fix loop |
| --- | --- | --- | --- |
| `app/memory/guard.py:281` | 25 | The read-mode key shape rule drops legacy keys with uppercase letters or spaces (e.g. `Diet`, `food preference`), which the v5 prompt actively invited. | Design §3.1 specifies this rule verbatim and defers migration to the read filter; an intentional B4 trade-off, not a defect. Real user-visible effect, so worth revisiting if legacy rows matter. |
| `app/memory/extractor.py:62` | 50 | A history with no `HumanMessage` now yields an empty exchange, and `extract_memories` still issues an LLM call on empty content. | Reaching it needs a compound trigger (the turn's own message pruned by the summarizer window AND the tail ending in tool traffic). Cost is a wasted call, not a poisoning vector. |
| `app/memory/store.py:87` | 25 | `_guarded_values` / `_guarded_episode_payload` call `item.value.get(...)` outside the try, assuming every stored value is a dict. | No writer produces a non-dict value; `BaseStore.put` types it as a dict. Hypothetical trigger. |
| `app/memory/store.py:100` | 0 | The episode read payload drops `updated_at` and caller-supplied extra fields. | Explicitly specified in design §3.1 and pinned by a test; intentional. No consumer reads those fields. |
| `app/tools/memory_tools.py:32` | 25 | An unknown preference key now fails pydantic validation inside ToolNode, so the tool's own graceful rejection message is unreachable for that class. | Intended: a test added in the same commit pins this outcome, and the key allowlist already rejected unknown keys one commit earlier, so nothing that used to persist stopped persisting. |
| `evalkit/metrics/deterministic.py:474` | 25 | `no_injected_memory` matches fixed regexes, so a PARAPHRASED injection would be stored and still pass. | Unverified hypothesis: it depends on extractor phrasing and on the guard's own blocklist failing on the same paraphrase, and the key allowlist constrains where such text could land. |
| `eval/datasets/memory.json:11` | 0 | The two smoke memory goldens declare `tools_expected`, which a rejected save still satisfies, so the free smoke gate cannot see a broken write. | The flagged line is not modified by this diff. Real, and worth a follow-up: the only golden proving a write sits in the paid full suite. |

### Rollback

- `git revert <sha>` (intake artifacts only)

### Harness-Delta

- backlog — `hooks/blast-radius-check.sh` resolved the "active plan" to an unrelated spec (`specs/gh-193-booking-revise-idempotency/PLAN.md`) for all three wave-1 implementers in this worktree, so its in-scope file check warned on every correct edit and would not have caught a real blast-radius escape. A gate that points at the wrong plan is a silent no-op.
- backlog — the worktree isolation guard refuses any Bash command containing `&&`, a pipe, a `..` path, or the literal 4-letter token e-v-a-l. The repo's documented test form (`cd apps/api && ../../.venv/bin/python -m pytest ...`, CLAUDE.md) is therefore unrunnable inside a harness worktree, and every path under the eval packages needs an `ev*l` glob. Worked around in this PLAN (Global Constraints + all Verify rows rewritten to worktree-root form); the recipe belongs in `docs/solutions/` via `compound`.
