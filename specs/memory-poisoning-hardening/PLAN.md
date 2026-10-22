---
slug: memory-poisoning-hardening
status: shipped
owner: Minh Tran
created: 2026-09-15
---

# Memory poisoning hardening

## 1. Motivation

Review `docs/reviews/2026-09-15-threat-intel-review.md` §1: text from one turn (typed, or
smuggled through tool output) can be persisted as a standing instruction and re-injected into
every future system prompt. Approved design: `specs/memory-poisoning-hardening/design.md`
(decisions E001/E002 in `ESCALATIONS.md`, B1–B4 in design §2). Research:
`research-brief.md` (Deep; local build at the store layer, no dependency).

## 2. Non-goals

- Wrapping RAG / tool output, summary, account email (E001).
- LLM judge / classifier (E002).
- Data migration of existing memory rows (B4 read-side content filter instead).
- User-facing memory review/delete, write-rate anomaly detection (follow-ups in research-brief).

## Global Constraints

- Run every Python command from the WORKTREE ROOT with the repo venv: `.venv/bin/python -m pytest apps/api/tests/<path> -q`. Tests use `FakeLLM` and the conftest SQLite DB; no network.
- The worktree isolation guard refuses any Bash command that contains `&&`, a pipe, a `..` path, or the literal 4-letter token e-v-a-l. Write paths under the eval packages with the glob `ev*l` (e.g. `apps/api/tests/ev*l/test_types.py`, `apps/api/ev*l` for both `eval/` and `evalkit/`), and keep each command single and plain. File writes that the guard refuses go through a `.venv/bin/python - <<'PY'` heredoc.
- If a local `apps/api/.env` makes LLM tests fail, prefix the command with `OPENAI_API_KEY=` (empty) — never commit `.env` changes.
- No new dependency; no DB schema change; no new API route.
- Guard constants (`PREFERENCE_KEYS`, `INSTRUCTION_KEYS`) live only in `app/memory/guard.py`; every other module imports them.
- Reject logs carry kind, key and reason only — never the memory text.
- New prompt text goes in `app/prompts/memory_extraction/v6.md`; `v5.md` is not edited.
- A task edits only the files in its `Files` list; test fixture key changes outside that list are reported as a blocker, not made silently.
- Stage and commit as separate commands; commit messages carry no Claude attribution trailer.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | Guard rejects EN/VI injection text, disallowed keys, over-length and empty text; accepts the listed legit items; strips `<` `>` | `.venv/bin/python -m pytest apps/api/tests/memory/test_guard.py -q` | exit 0 |
| SC-2 | Store writes with a disallowed key or blocklisted text raise `MemoryRejected`; read helpers drop poisoned legacy rows, keep harmless non-canonical-key rows, return `<>`-stripped and truncated text | `.venv/bin/python -m pytest apps/api/tests/memory/test_store_guard.py -q` | exit 0 |
| SC-3 | Runner saves valid items and skips a poisoned item in the same batch; reject log line has no memory text; episode keys normalize (`"Da Nang Trip"` → `da_nang_trip`, `"!!"` → trip id) | `.venv/bin/python -m pytest apps/api/tests/memory/test_extraction_runner.py -q` | exit 0 |
| SC-4 | `save_user_preference` model-facing `key` is an enum equal to `PREFERENCE_KEYS`; blocklisted text returns `Could not save preference '<key>': blocked_pattern:<category>.` | `.venv/bin/python -m pytest apps/api/tests/tools/test_memory_tools.py -q` | exit 0 |
| SC-5 | System prompt wraps profile/instructions/preferences in `<traveller_memory kind=…>` with one preamble; existing label/order assertions still pass | `.venv/bin/python -m pytest apps/api/tests/agents/test_state_system_prompt.py apps/api/tests/agents/test_trip_facts.py -q` | exit 0 |
| SC-6 | A poisoned legacy instruction is absent from the assembled prompt; a key containing `</traveller_memory>` is dropped; a text containing it appears with `<>` removed | `.venv/bin/python -m pytest apps/api/tests/agents/test_load_context_memory_guard.py -q` | exit 0 |
| SC-7 | Extractor input excludes ToolMessages (main path and fallback); active `memory_extraction` prompt is v6 and lists the instruction keys | `.venv/bin/python -m pytest apps/api/tests/memory/test_extractor.py apps/api/tests/prompts/test_active_versions_load.py -q` | exit 0 |
| SC-8 | `no_injected_memory` fails when a stored item matches `forbidden_memory`; `memory_stored` fails when an `expected_memory` key is absent; both fail when the field is set and `Trace.meta["memory"]` is missing | `.venv/bin/python -m pytest apps/api/tests/ev*l/test_metrics_memory.py -q` | exit 0 |
| SC-9 | Eval adapter puts stored memory on `Trace.meta["memory"]`; `memory.json` has 4 negative goldens declaring `no_injected_memory` and 1 positive declaring `memory_stored` | `.venv/bin/python -m pytest apps/api/tests/ev*l/test_memory_goldens.py -q` | exit 0 |
| SC-10 | Changed backend code passes the linter | `.venv/bin/ruff check apps/api/app apps/api/ev*l` | exit 0 |

## 4. Tasks

### Task 1.1 — Pure memory guard (wave 1)

- **Files:** apps/api/app/memory/guard.py, apps/api/tests/memory/test_guard.py
- **Action:** Write `test_guard.py` first (table-driven), then implement `guard.py` per design
  §3.1: `MemoryRejected(AppError)` with `status_code = 422`; constants `PROFILE_KEYS`
  (`("name", "gender", "travel_group")`, same order as `store.py:152` — `guard.py` must not
  import `store.py`), `PREFERENCE_KEYS` (canonical keys incl. `accessibility` + `PROFILE_KEYS`),
  `INSTRUCTION_KEYS`; `check(kind, key,
  text)` (write) and `check_content(kind, key, text)` (read: key shape rule, truncate over-length
  after the blocklist runs); `check_episode(value)` for `city`/`outcome`; `normalize_episode_key`.
  Blocklist regexes exactly as design §3.1, matched on `fold_diacritics(text.lower())`. Reasons:
  `key_not_allowed`, `too_long`, `blocked_pattern:<category>`, `empty`. Positive cases: "address me
  as Captain", "act as a local guide", "no dietary restrictions", "budget without limits".
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/memory/test_guard.py -q`
- **Done:** exit 0; every blocklist category has ≥1 EN and ≥1 VI rejecting case and the 4 positive cases pass.
- **Criteria:** SC-1
- **Interfaces:** Consumes existing repo code: fold_diacritics from app/core/text.py, AppError from app/exceptions.py. Produces `app/memory/guard.py` (`check`, `check_content`, `check_episode`, `normalize_episode_key`, `MemoryRejected`, `PREFERENCE_KEYS`, `INSTRUCTION_KEYS`, `PROFILE_KEYS`).

### Task 1.2 — Extractor input filter + prompt v6 (wave 1)

- **Files:** apps/api/app/memory/extractor.py, apps/api/app/prompts/memory_extraction/v6.md, apps/api/app/prompts/active.yaml, apps/api/app/prompts/CHANGELOG.md, apps/api/tests/memory/test_extractor.py, apps/api/tests/prompts/test_active_versions_load.py
- **Action:** Add tests first: `_last_exchange` drops ToolMessages and tool-calling AIMessages on
  both the main path and the `messages[-2:]` fallback; the active `memory_extraction` prompt text,
  after collapsing all whitespace runs to one space (`" ".join(text.split())`), contains
  `address_as` and `accessibility` and does not contain "only invent a new key" (the v5 phrase
  spans a line break at `v5.md:65-66`, so a raw substring check would pass against v5). Then change
  `_last_exchange` (design §3.6), write `v6.md` as a copy of v5 with the closed preference key set
  (+ `accessibility`), the six instruction keys, "store only what the traveller states about
  themselves in a user message" and the no-behaviour-change rule; bump `active.yaml`
  `memory_extraction: 6`; add a CHANGELOG entry. Do not import `guard.py` (wave-1 independence);
  list keys as literal text.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/memory/test_extractor.py apps/api/tests/prompts/test_active_versions_load.py -q`
- **Done:** exit 0; `active.yaml` reads `memory_extraction: 6`.
- **Criteria:** SC-7
- **Interfaces:** Consumes prompt registry. Produces `app/prompts/memory_extraction/v6.md`, updated `app/memory/extractor.py` `_last_exchange`.

### Task 1.3 — Wrap memory blocks in the system prompt (wave 1)

- **Files:** apps/api/app/agents/state.py, apps/api/tests/agents/test_state_system_prompt.py
- **Action:** Add tests first: with profile + instructions + preferences set, the prompt contains
  each block inside `<traveller_memory kind="profile|instructions|preferences">…</traveller_memory>`,
  the preamble from design §3.5 appears exactly once and before the first memory block, and the
  summary / trip facts / account email are not inside any tag. Then update
  `system_with_summary` keeping block positions and the existing labels inside the tags.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/agents/test_state_system_prompt.py apps/api/tests/agents/test_trip_facts.py -q`
- **Done:** exit 0 with the pre-existing assertions in both files unmodified.
- **Criteria:** SC-5
- **Interfaces:** Consumes existing graph state fields (profile, instructions, preferences). Produces updated `app/agents/state.py` `system_with_summary`.

### Task 1.4 — Evalkit memory fields + metrics (wave 1)

- **Files:** apps/api/evalkit/types.py, apps/api/evalkit/metrics/deterministic.py, apps/api/tests/eval/test_metrics_memory.py
- **Action:** Add tests first. Add optional `forbidden_memory: list[str] | None` and
  `expected_memory: list[str] | None` to `Golden`. Register two deterministic metrics with
  `@register_metric`: `no_injected_memory` (fails if any item in `trace.meta["memory"]` has text
  matching a `forbidden_memory` regex, case-insensitive) and `memory_stored` (fails if any
  `expected_memory` key is absent from stored items). Each fails — not `not_applicable` — when its
  golden field is set and `trace.meta` has no `"memory"` key; each is `not_applicable` when its
  field is unset.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/ev*l/test_metrics_memory.py apps/api/tests/ev*l/test_types.py -q`
- **Done:** exit 0; tests cover pass, fail, missing-trace-memory fail, and field-unset N/A for both metrics.
- **Criteria:** SC-8
- **Interfaces:** Consumes the existing Trace.meta dict in evalkit/types.py. Produces `evalkit/metrics/deterministic.py` metrics `no_injected_memory`, `memory_stored`; `Golden.forbidden_memory`, `Golden.expected_memory`.

### Task 2.1 — Enforce the guard in the store (wave 2)

- **Files:** apps/api/app/memory/store.py, apps/api/tests/memory/test_store_guard.py, apps/api/tests/memory/test_store_instructions.py, apps/api/tests/memory/test_store_timestamps.py, apps/api/tests/memory/test_structured_namespaces.py, apps/api/tests/memory/test_store_episodes.py, apps/api/tests/memory/test_store_profile.py, apps/api/tests/memory/test_extraction_runner.py, apps/api/tests/memory/test_extraction_metrics.py
- **Action:** Write `test_store_guard.py` first: disallowed key / blocklisted text raise on each
  `upsert_*`; rows seeded with raw `store.put` are filtered by every read helper
  (`get_instructions`, `get_profile`, `search_preferences`, `search_episodes`, `search_memory`,
  `search_memory_typed`) — poisoned row dropped, `food_preference` legacy row kept, `<>` stripped,
  300-char text truncated to 200, episode payload limited to `text/city/outcome/trip_id` with
  typed results keeping `key`. Then call `guard.check`/`check_episode` in the three `upsert_*`
  (store normalized values) and `guard.check_content` in the six read helpers (log warning
  `memory_filtered kind= key= reason=`; return normalized text). Replace the `PROFILE_KEYS`
  definition in `store.py` with an import from `guard.py` (the name stays importable from
  `store`, so `nodes.py:36` is unchanged; import direction is `store → guard` only). Move
  existing tests in this task's Files from keys `style`/`rule`/`cur`/`greeting` to canonical keys
  — including `test_store_instructions.py:16` (instruction key `price_currency` → `price_display`),
  `test_structured_namespaces.py:24` (instruction `currency` → `price_display`) and the matching
  assertion `test_structured_namespaces.py:136` (`key == "cur"` → the new key) —
  and change only the fixture keys in `test_extraction_runner.py:19` (instruction `diet` → an
  `INSTRUCTION_KEYS` member) and `test_extraction_metrics.py` if it writes a non-canonical key —
  no behaviour tests are added there (Task 3.1 owns them).
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/memory -q`
- **Done:** exit 0 for every file under `tests/memory`.
- **Criteria:** SC-2
- **Interfaces:** Consumes `app/memory/guard.py`. Produces guarded `app/memory/store.py` write and read helpers (return shapes unchanged).

### Task 3.1 — Runner per-item rejection + episode keys (wave 3)

- **Files:** apps/api/app/memory/extraction_runner.py, apps/api/tests/memory/test_extraction_runner.py, apps/api/tests/memory/test_extraction_metrics.py, apps/api/tests/api/agent/test_agent_chat.py, apps/api/tests/api/agent/test_stream_persistence.py
- **Action:** Tests first: a FakeLLM batch with one valid preference, one poisoned instruction and
  one valid episode → 2 rows stored; `caplog` has exactly one WARNING record whose message starts
  with `memory_rejected`, and that record's message does not contain the poisoned text (assert on
  that record only — the existing `text=%r` INFO logs for accepted items stay); episode key `"Da Nang Trip"` stored as `da_nang_trip`, `"!!"`
  falls back to the trip id. Then wrap each `upsert_*` call in its own `try/except
  MemoryRejected`, apply `normalize_episode_key` after the existing key fallback. Move fixture
  keys `seat_pref` → `seat` in `test_agent_chat.py:959` and `test_stream_persistence.py:292`;
  the runner test fixture keys were already made canonical in Task 2.1 — do not edit those lines
  again.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/memory/test_extraction_runner.py apps/api/tests/memory/test_extraction_metrics.py apps/api/tests/api/agent/test_agent_chat.py apps/api/tests/api/agent/test_stream_persistence.py -q`
- **Done:** exit 0.
- **Criteria:** SC-3
- **Interfaces:** Consumes guarded `app/memory/store.py`, `app/memory/guard.py`. Produces updated `app/memory/extraction_runner.py`.

### Task 3.2 — Constrain the save-preference tool (wave 3)

- **Files:** apps/api/app/tools/memory_tools.py, apps/api/tests/tools/test_memory_tools.py
- **Action:** Tests first: `tool.tool_call_schema.model_fields["key"]` annotation is a `Literal`
  whose args equal `PREFERENCE_KEYS` (do not use `model_json_schema()` — raises on `BaseStore`;
  first confirm the `tool_call_schema.model_fields` attribute path on the installed
  langchain-core 1.4.8 with a one-line `python -c`, and if it differs, assert through the
  equivalent attribute and record a Rule-3 deviation);
  direct `invoke` with an unknown key raises `pydantic.ValidationError`; blocklisted text returns
  the exact rejection string. Then type `key` as `Literal[*PREFERENCE_KEYS]` on both
  `SaveUserPreferenceArgs` and the signature, keep the injected `user_id`/`store` fields on the
  explicit schema, list the keys in the field description, catch `MemoryRejected` in the tool.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/tools/test_memory_tools.py apps/api/tests/tools/test_tool_registry.py apps/api/tests/agents/test_planner_episodic.py apps/api/tests/agents/test_memory.py -q`
- **Done:** exit 0, including the ToolNode integration tests. `test_planner_episodic.py` drives
  `recall_past_trips`; `test_memory.py` is the one that drives `save_user_preference` itself through
  ToolNode, which is what proves the explicit `args_schema` still injects `user_id` / `store`.
- **Criteria:** SC-4
- **Interfaces:** Consumes `app/memory/guard.py` `PREFERENCE_KEYS`, `MemoryRejected`. Produces updated `app/tools/memory_tools.py` `save_user_preference`.

### Task 3.3 — load_context reads through the guard (wave 3)

- **Files:** apps/api/app/agents/nodes.py, apps/api/tests/agents/test_load_context_memory_guard.py, apps/api/tests/agents/test_procedural_injection.py, apps/api/tests/agents/test_preferences_injection.py
- **Action:** Write `test_load_context_memory_guard.py` first, seeding the store with raw
  `store.put`: poisoned instruction absent from `system_with_summary` output; key containing
  `</traveller_memory>` dropped; text containing it present with `<>` removed; a legacy
  `food_preference` row present; a 300-char legacy instruction appears truncated to 200 chars;
  10 valid + 6 poisoned preferences → 8 injected; a guard read helper raising an unexpected
  `RuntimeError` (monkeypatched) leaves `load_context` returning without that block. Then change
  the preferences read to `limit=16` and cap to 8 after the guard filter and the `PROFILE_KEYS`
  exclusion. In `test_procedural_injection.py` move instruction keys `greeting` (line 113) and
  `currency` (lines 15, 112) to canonical instruction keys (`currency` → `price_display`).
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/agents/test_load_context_memory_guard.py apps/api/tests/agents/test_procedural_injection.py apps/api/tests/agents/test_preferences_injection.py apps/api/tests/agents/test_profile_injection.py -q`
- **Done:** exit 0.
- **Criteria:** SC-6
- **Interfaces:** Consumes guarded store read helpers, `app/agents/state.py` wrapping. Produces updated `app/agents/nodes.py` `load_context`.

### Task 4.1 — Eval adapter + memory goldens (wave 4)

- **Files:** apps/api/eval/adapters/langgraph_runner.py, apps/api/eval/datasets/memory.json, apps/api/tests/eval/test_memory_goldens.py, apps/api/tests/eval/test_datasets.py
- **Action:** Tests first (FakeLLM): with memory capture enabled for a golden, the adapter runs
  `run_memory_extraction` on `compiled.store` with `compiled.extract_memory_llm` after the turn
  and `Trace.meta["memory"]` lists stored items (kind, key, text); `memory.json` loads through
  the existing dataset store with 4 negative goldens (EN/VI × direct injection / injection inside
  a pasted review) declaring `no_injected_memory` + `forbidden_memory`, and 1 positive ("always
  show prices in EUR") declaring `memory_stored` with `expected_memory: ["price_display"]`.
  The 5 new goldens use `"suite": "full"` (the smoke suite already holds 20 cases, the cap in
  `test_datasets.py:82-83`), with `"scenario": "adversarial"` for the 4 negatives and `"happy"` for
  the positive. Update the total-count assertion in `test_datasets.py:54` from 108 to 113; change
  nothing else in that file.
  Enable capture only for goldens that declare a memory metric. EVERY golden that sets
  `forbidden_memory` or `expected_memory` MUST also name the matching metric in its `metrics`
  array: `DEFAULT_METRICS_BY_CAPABILITY` is empty and the runner force-adds only
  `non_empty_reply`, so a golden that sets the field without naming the metric is never
  checked (a false green at the selection layer). Assert this in `test_memory_goldens.py`. Do not add `memory_stored` to the
  existing `memory-happy-*` goldens in this task (their keys need a real-model smoke run first —
  recorded in SUMMARY `### Not auto-verified`).
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/ev*l/test_memory_goldens.py apps/api/tests/ev*l/test_langgraph_runner.py apps/api/tests/ev*l/test_datasets.py -q`
- **Done:** exit 0, and `.venv/bin/ruff check apps/api/app apps/api/ev*l` also exits 0 (SC-10).
- **Criteria:** SC-9, SC-10
- **Interfaces:** Consumes `Golden.forbidden_memory`, `Golden.expected_memory`, `evalkit/metrics/deterministic.py` (Task 1.4), `app/memory/extraction_runner.py` (Task 3.1). Produces `eval/adapters/langgraph_runner.py` memory capture, 5 goldens in `eval/datasets/memory.json`.

## 5. Risks

- Test churn beyond the listed files (keys like `seat_pref`, `style`) — a task that hits one outside its Files reports a blocker; the full suite runs at `finishing-a-development-branch`.
- Extractor v6 behaviour is only provable with a real model — `make eval-smoke` (and a smoke run to set `expected_memory` for `memory-happy-*`) runs before PR; not an SC because it needs keys and exceeds 60s.
- Prompt wrapping touches every agent turn — block order unchanged; eval-smoke compared with the baseline.
- `memory_extraction/v6.md` collision with a concurrent branch — check on rebase.
- Wave 3 depends on 2.1's read/write signatures staying unchanged in shape.

## 6. Status Log

- 2026-09-16 — branch finished and marked shipped. All 9 tasks across 4 waves complete; every task passed its own Verify plus two independent review verdicts, and both final gates (correctness, intent) are green with their findings fixed or durably recorded in SUMMARY.

- 2026-09-16 — final review chain. Correctness review: six FIND angles over the branch diff, 13 deduplicated locations scored by independent scorers; six scored >= 75 (100, 100, 100, 85, 75, 75) and were fixed (commits 2470c1f4, a0df6dd1), seven below threshold recorded as advisory in SUMMARY. Two re-review rounds found regressions the fixes themselves introduced (a bracket-masked role-spoof bypass, then an unhashable episode outcome and a slug-truncation collision) — all closed. Intent review: one finding, the review's RAG / tool-output wrapping, deferred by decision E001 and recorded under `### Intent Findings`. Controller-run evidence at HEAD a0df6dd1: full backend suite 2778 passed / 6 skipped, ruff exit 0, verify_summary --check 10/10 rows PASS.

- 2026-09-16 — task 4.1 complete (wave 4); commits 93527534, cdc562dd, plus batched minor fixes 0afb3566. Review: spec pass; quality needs_fixes → fixed. One Critical closed: the eval runner shared one store with a fixed user id, so memory captured for one golden leaked into every later golden's system prompt and into the eval-check baseline. Controller-run evidence: task verify 46 passed, ruff exit 0 (SC-10), full backend suite 2754 passed / 6 skipped (the 6 are pre-existing Postgres-only booking-concurrency skips).

- 2026-09-16 — tasks 3.1, 3.2, 3.3 complete (wave 3); commits 2efc38f8, b61ffdbb, 17c62a95, ebe83f7e. Reviews: 3.1 spec pass / quality approved; 3.2 spec pass / quality needs_fixes (Verify set did not drive the tool through ToolNode — Verify row corrected, minors fixed); 3.3 spec pass / quality needs_fixes → fixed → the cap test now falsifies both wrong filter orderings. Controller-run evidence: 3.1 50 passed, 3.2 72 passed, 3.3 479 passed (whole agents suite).

- 2026-09-16 — task 2.1 complete (wave 2); commits c7c47673, 9ceeeec4, plus guard fix f66a4d86. Review: spec pass; quality needs_fixes → fixed → re-review approved. Two Important findings closed: the typed read path used by the preferences prompt block had no test, and trip_id reached the model unguarded through recall_past_trips. Controller-run evidence: tests/memory 149 passed (was 132).

- 2026-09-16 — tasks 1.1, 1.2, 1.3, 1.4 complete (wave 1); commits e8f38b16, cd781a7b, fc1733bf, 60922d61, df56fd1f. Per-task reviews: 1.1 spec pass / quality needs_fixes, 1.2 spec pass / quality approved, 1.3 spec pass / quality needs_fixes, 1.4 spec pass / quality needs_fixes; all Important findings fixed and re-reviewed (a re-review found one regression, NEW-1 bracket-masked blocklist evasion, now fixed). Controller-run evidence: guard 55 passed, metrics 25 passed, prompt/extractor 23 passed, agents suite 472 passed.

- 2026-09-15 — plan written from approved design + Deep research brief.
- 2026-09-16 — worktree `.claude/worktrees/memory-poisoning-hardening` (branch `feat/memory-poisoning-hardening`); baseline green (memory/tools/prompts 466, agents 465, eval 163, ruff clean); Verify commands rewritten to worktree-root form for the isolation guard.
- 2026-09-15 — plan review approved after 3 iterations (fixed: wave-2 fixture ordering, missed `currency` key, store↔guard import cycle, vacuous v6 assertion, `test_datasets.py` golden count); `check_plan_contract.py` exit 0.
