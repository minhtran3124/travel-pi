# SUMMARY — user-feedback-v1

Lane: high-risk
Confidence: high
Reason: Implementation round (2026-09-12) trips three block-mode hard gates — data-loss/migration (Alembic migration adding `messages.agent_run_id` + `feedback_events`), public-contract (new `POST /agent/feedback`, additive fields on `/agent/chat`, SSE `done`, history), audit/security (feedback comments are user free text with privacy rules). Confidence high: design approved and re-based, user set the scope explicitly.
Flags: data-model, public-contract, audit/security, existing-behavior, multi-domain
Affects: apps/api routers agent/feedback, streaming persistence, conversation repository, messages table; apps/web chat components, SSE parser, messages en/vi
Input-type: spec slice
Route: using-git-worktrees → subagent-driven-development (design.md = DESIGN.md, research-brief = RESEARCH.md, PLAN.md re-based 2026-09-12)
Escalate: no (scope fixed by the user; no ambiguity left after the 2026-09-12 revision)

### Intent

User request, verbatim, 2026-09-12 (chronological):

> check for "Feedback learning v1 còn là bản nháp chưa commit"

> làm bước 2, sửa DESIGN/PLAN theo agent_runs hiện có

> việc feedback loop từ user có effect vs chatbot hien tai ko? neu co thi ntn?

> ok, lam phan UI + BE api truoc, ko effect voi chatbot

Prior intake (2026-07-21, documentation turn): Lane normal, Confidence high — "This turn creates
research/design documentation only. The designed implementation is high-risk because it includes a
migration and public REST/SSE contract changes."

## Rationale

The foundation must solve stable answer identity, authorization, idempotency, privacy, and accessible
stateful UX before any feedback is allowed to influence memory. SQL is the product source of truth;
Langfuse is an optional evaluation projection. An append-only event log preserves corrections and
retractions without silently rewriting what the user did.

Revision 2026-09-12: the run-provenance table the design proposed already exists on `main`
(`agent_runs`, PR #131, migration `e3b7c5d9a1f4`; `agent_run_steps` + `prompt_versions`, PR #132,
migration `b2d9f4a7c1e8`). Creating it again would collide on the table name and the model class.
The design and plan now extend the existing tables with two nullable columns
(`messages.agent_run_id`, `agent_runs.trace_id`) and create only `feedback_events`. The `429`
abuse limit the contract promised but no task delivered (REVIEW.vi.md gap #1) is now Task 3.2 over
the PR #110 primitive and the `feedback_rate_limit_*` settings that already exist in
`app/core/config.py`. The REST lifecycle gap (REVIEW gap #3) closes because the chat router already
starts and finishes the run row on the request session. The anonymous-claim gap (REVIEW gap #2)
becomes an explicit `reassign_user` extension in Task 2.1.

## Alternatives

- Put a learning agent behind the supervisor — rejected because feedback capture is cross-cutting,
  not a travel intent.
- Store only one mutable rating row — rejected because it loses change/retraction audit history.
- Send browser feedback directly to Langfuse — rejected because it couples a product action and
  ownership policy to an optional external system.
- Use the FE's temporary bubble UUID — rejected because it is not the persisted message identity.
- Persist an empty assistant row before streaming — rejected because aborted streams would create
  misleading history.
- (2026-09-12) Keep a separate feedback-owned run table beside `agent_runs` — rejected: two rows per
  turn with the same lifecycle, and the metrics dashboard would not see the feedback side.
- (2026-09-12) Put the message link on the run (`agent_runs.assistant_message_id`, unique) — rejected
  in favour of `messages.agent_run_id`: the message is the feedback target, a one-way link on the
  child row is the repo precedent, and a unique constraint would fight a retried turn.
- (2026-09-12) Add an `abandoned` run status — rejected: the existing recorder already marks a
  disconnect `failed`, and the feedback path only tests "not `completed`".

## Outcome

- Audited the existing BE message, stream persistence, ownership, memory, tracing, migration, FE
  hydration, SSE parsing, identity, UI primitive, i18n, and test seams.
- Defined the v1 event state machine, SQL model, API/SSE/history contracts, privacy rules, UX states,
  rollout, observability projection, metrics, and BE-to-FE test matrix.
- Added synchronized English/Vietnamese research and design documents.
- Added a wave-based high-risk implementation plan; no runtime code or schema was changed.
- 2026-09-12: re-based DESIGN.md / DESIGN.vi.md §2, §3.1, §3.4, §4.2, §4.3, §5.2, §9, §11, §12 and
  rewrote PLAN.md (7 tasks, 7 waves, Global Constraints + 16 Success Criteria per
  `rules/plan-format.md`) on the `agent_runs` / `agent_run_steps` tables that shipped after the
  original draft. Still documentation-only; still `proposed`. RESEARCH.md was not edited: its
  audit predates PR #131 and is kept as the record of what was true on 2026-07-21.

### Implementation progress (2026-09-12)

- Wave 1 — Task 1.1 commit `450acd3`: schema + migration `d4f7a2c9e1b3`. Task review: spec pass /
  quality approved; 4 Minor recorded in `.harness-state/sdd/minor-findings.md` (Postgres run pending,
  per-action rules live in the service, `updated_at` by convention, reason_code taxonomy confirmed as
  incorrect | irrelevant | incomplete | unsafe | other).
- Wave 2 — Task 2.1: `FeedbackRepository`, `append_message(message_id, agent_run_id)`,
  `get_message_for_feedback`, three-table `reassign_user`, feedback schemas. Verify `tests/db`
  63 passed; regression set 43 passed. Landed as `14edffa` (lane read from the staged SUMMARY;
  no gate category loosened). Task review: spec pass / quality approved; 4 Minor in the ledger
  (`reason_code` typing in `_fold` to fix post-wave-3, `locale` allowlist moved to the service).
- Wave 3 — Task 3.1: `assistant_message_id` + `agent_run_id` on `/agent/chat`, SSE `done` yielded only
  after the assistant row is committed, history items carry `feedback`. Rule-1 deviation: a `done`
  that follows an `interrupt` passes through with `assistant_message_id: null` (DESIGN §4.2) instead of
  becoming `error{empty_reply}` as a literal reading of §4.3 implied. Verify `tests/api/agent
  tests/streaming` 167 passed. Landed as `1298433`. Task review: spec pass / quality needs_fixes —
  one Important (a failed SSE turn no longer persisted its fallback text because the mapper never
  emits `done` on failure): decided to persist on terminal `error` with non-empty text (run is
  `failed`, never rateable), DESIGN §4.3 amended (en + vi). Fix landed in the next change together
  with a resume-path identity test and a rule that `error{code: cancelled}` (client disconnect)
  never writes a row. `tests/api/agent tests/streaming` 201 passed after the fix.
- Wave 3 — Task 3.2: `FeedbackService`, `POST /agent/feedback` (router registered in
  `app/routers/main.py`, the aggregate the app mounts — deviation from the plan's `app/main.py`),
  feedback abuse limit over the PR #110 primitive (`enforce_rate_limit` called directly with a
  body-aware `feedback_subject`, per the primitive's own docstring), import-graph test proving no
  feedback → memory edge, `locale` allowlist from `app/core/languages.py`. Verify 30 passed; whole
  `tests/api/agent` 148 passed. Landed as `2cb7174`. Task review: spec pass / quality approved;
  4 Minor (export-hook ordering vs teardown commit and retract-no-op semantics recorded in DESIGN
  §9/§5.2; `append` inserted-flag and store forbidden-prefix fixed in the review-fixes change).
- Wave 4 — Task 4.1: `schema.d.ts` regenerated offline from `app.openapi()` (the :8000 container
  mounts main), `lib/query/feedback.ts` (`useSubmitFeedback`, one `clientEventId` per logical action,
  per-message in-flight guard, `retry()`), SSE `done` gains the two ids, terminal codes parse as
  errors. Verify 59 tests / 10 files, `tsc --noEmit` 0, eslint 0. Deviation: no query key added
  (`keys.ts` untouched — there is no feedback query, only a mutation). Landed as `905a3c4`. Task
  review: spec pass / quality approved; 4 Minor (two are constraints handed to Task 5.1: disable a
  message's controls while pending, derive per-message status from the returned promise).
- Review-fixes change (backend Minors M5, M13, M15): `_fold` rebuilds `EffectiveFeedback` through
  validation so `reason_code` is always the enum (retired codes fold to `other`);
  `FeedbackRepository.append` returns `(event, inserted)` and an identical-payload race now answers
  `200 replayed: true` with no log line and no export; the no-memory-edge test also forbids
  `langgraph.store` and documents the surfaces it covers. `tests/db tests/api/agent/test_feedback*
  tests/architecture tests/api/agent/test_agent_chat.py` 128 passed. Landed as `5afa5d8`. Review:
  spec pass / quality approved; 4 optional Minor in the ledger.
- Postgres: full backend suite on Postgres 17 / Python 3.12 at `5afa5d8` (isolated compose project,
  worktree mounted into the cached test image): 2538 passed, 0 failed.
- Wave 5 — Task 5.1 landed as `5cfe366`: `MessageFeedback` + `FeedbackDialog` under complete
  assistant replies with a server id, optimistic update with rollback and same-id retry, per-message
  disable while pending, 404 hides the controls, en/vi strings. Controller re-ran `tsc --noEmit`
  (0), `eslint src/components/chat` (0 errors, 1 warning under review), and the three Verify test
  files: 24 passed. Whole web suite 54 files / 332 tests passed. Task review: spec fail / quality
  needs_fixes — one Important (after a successful detail Save the dialog's trigger unmounts, so focus
  restore lands on a detached node and falls to `<body>`, breaking DESIGN §8.4) plus five Minor
  (dialog reopening on a late failure, empty-content gate, hook-level id tests, textarea error
  association, the `feedback` field missing from the hand-written history type). All six sent to one
  fix round; the `exhaustive-deps` warning at `useAgentStream.ts:329` is pre-existing (2026-09-02).
- Task 5.1 fix round: focus moves to the pressed Not-helpful button after a successful detail Save;
  a detail failure after the user closed the dialog surfaces inline with Retry instead of reopening it;
  controls also require non-empty content and a Stop after `done` clears the id; hook-level tests for
  `done` with / without an id and for hydration; textarea error in `aria-describedby`; the history
  `feedback` field added to the hand-written `Message` type (cast removed). Rule 2: the three duplicated
  stop-handling blocks folded into one `settleTurn()` helper. `pnpm test src/components/chat` 154
  passed; whole web suite 340 passed; tsc and eslint clean apart from the pre-existing warning.
  Re-review: spec pass / quality approved. Two of its three Minor fixed in a follow-up: a background
  detail success that unmounts the trigger now moves focus to Not-helpful only when focus was on the
  trigger or `<body>`; a hook test's stale array moved inside `waitFor`. The third (reopening the
  dialog after a closed-dialog failure leaves the old inline error) is recorded, not fixed.

## Deviations

- Rule 1 — `persist_assistant_turn`: a `done` that follows an `interrupt` passes through with
  `assistant_message_id: null` (DESIGN §4.2) instead of becoming `error{empty_reply}`. Commit `1298433`.
- Rule 1 — failed SSE turns persist the streamed fallback text before `error` (review Important,
  DESIGN §4.3 amended); `error{code: cancelled}` writes nothing. Commit `bce70d8`.
- Rule 2 — terminal error codes `empty_reply` / `persistence_failed` chosen by the implementer and then
  recorded in DESIGN §4.3. Commit `1298433`.
- Rule 2 — `locale` allowlist enforced in `FeedbackService` from `app/core/languages.py` (review of
  Task 2.1). Commit `2cb7174`.
- Plan deviation — `POST /agent/feedback` registered in the aggregate `app/routers/main.py`, not
  `app/main.py`, because the app mounts only the aggregate. Commit `2cb7174`.
- Plan deviation — the feedback limit calls `enforce_rate_limit` directly with a body-aware subject
  (`anon:<id>` for anonymous callers), as the primitive's own docstring prescribes; it still runs
  before the request session opens a transaction. Commit `2cb7174`.
- Plan deviation — `apps/web/src/lib/api/keys.ts` untouched: the feedback hook has no query to key.
  Commit `905a3c4`.
- Plan deviation — `schema.d.ts` regenerated offline from `app.openapi()` because the :8000 container
  mounts the main checkout. Commit `905a3c4`.
- Rule 1/2 review fixes — `_fold` typed `reason_code`, `append` returns `(event, inserted)` so an
  identical-payload race replays, wider no-memory import gate. Commit `5afa5d8`.
- Rule 2 — three duplicated stop-handling blocks in `useAgentStream.ts` folded into `settleTurn()`
  (reviewer confirmed behaviour-preserving). Commit `b534049`.
- Test-only — `tests/api/agent/test_agent_chat.py` history test adapted to the tuple return of
  `append`. Commit `5afa5d8`.

### Verify

Documentation checks (first seven rows) date from the 2026-09-12 re-base. `SC-1` … `SC-14` rows were
run from the repo root at `5cfe366` by the controller; `verify_summary.py --check` re-runs every row
at the final HEAD. `SC-15` (e2e collection) is added when Task 6.1 lands.

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Whitespace hygiene | `if rg -n '[[:blank:]]+$' specs/user-feedback-v1; then exit 1; fi` | 0 | No trailing whitespace in the spec folder | |
| Research section parity | `test "$(rg -c '^## ' specs/user-feedback-v1/RESEARCH.md)" = "$(rg -c '^## ' specs/user-feedback-v1/RESEARCH.vi.md)"` | 0 | 14 top-level sections each | |
| Design section parity | `test "$(rg -c '^## ' specs/user-feedback-v1/DESIGN.md)" = "$(rg -c '^## ' specs/user-feedback-v1/DESIGN.vi.md)"` | 0 | 13 top-level sections each | |
| External-source parity | `python3 -c "import re,sys;a=set(re.findall(r'https://[^)]+',open('specs/user-feedback-v1/RESEARCH.md').read()));b=set(re.findall(r'https://[^)]+',open('specs/user-feedback-v1/RESEARCH.vi.md').read()));sys.exit(0 if a==b else 1)"` | 0 | Both versions retain the same official source URLs | |
| Plan context contract | `python3 .claude/scripts/check_plan_contract.py specs/user-feedback-v1/PLAN.md` | 0 | Global Constraints, SC table, Criteria/Interfaces on all 7 tasks; every consumed artifact has a producer | |
| Design cites real code | `python3 -c "import os,sys;p=['apps/api/app/db/models/agent_run.py','apps/api/app/db/models/agent_run_step.py','apps/api/app/streaming/agent_run.py','apps/api/app/core/rate_limit.py','apps/api/alembic/versions/e3b7c5d9a1f4_add_agent_runs.py','apps/api/alembic/versions/b2d9f4a7c1e8_add_agent_run_steps.py','apps/api/alembic/versions/b8e4c1f7a305_add_bookings_trip_id.py','apps/api/tests/api/agent/test_agent_runs.py','apps/api/tests/api/agent/test_agent_run_steps_wiring.py','apps/api/tests/db/test_bookings_trip_id_migration.py'];m=[x for x in p if not os.path.exists(x)];print(m);sys.exit(1 if m else 0)"` | 0 | Every file the revised §3.1 / §11 / §12 name exists on main | |
| No second `agent_runs` table planned | `rg -c 'create_table\("agent_runs"' specs/user-feedback-v1/PLAN.md specs/user-feedback-v1/DESIGN.md` | 1 | rg exit 1 = zero matches, the intended result | |
| SC-1 The migration adds messages.agent_run_id and feedback_events, and  | `cd apps/api && ../../.venv/bin/python -m pytest tests/db/test_feedback_events_migration.py -q` | 0 | run 2026-09-12 at 5cfe366 | SC-1 |
| SC-2 ORM column sets for messages and feedback_events match the migrati | `cd apps/api && ../../.venv/bin/python -m pytest tests/test_db_models.py -q` | 0 | run 2026-09-12 at 5cfe366 | SC-2 |
| SC-3 Set, replace, detail, retract fold to the documented effective state | `cd apps/api && ../../.venv/bin/python -m pytest tests/db/test_feedback_repository.py -q` | 0 | run 2026-09-12 at 5cfe366 | SC-3 |
| SC-4 A conversation claim moves conversations, agent_runs and feedback | `cd apps/api && ../../.venv/bin/python -m pytest tests/db/test_conversation_reassign.py -q` | 0 | run 2026-09-12 at 5cfe366 | SC-4 |
| SC-5 /agent/chat, SSE done and reloaded history carry the same assista | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_agent_chat.py tests/api/agent/test_stream_events.py tests/streaming/test_persistence.py -q` | 0 | run 2026-09-12 at 5cfe366 | SC-5 |
| SC-6 POST /agent/feedback returns 201/200/404/409/422 per DESIG | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_feedback.py -q` | 0 | run 2026-09-12 at 5cfe366 | SC-6 |
| SC-7 The feedback_rate_limit_max + 1-th request in one window from the sa | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_feedback_rate_limit.py -q` | 0 | run 2026-09-12 at 5cfe366 | SC-7 |
| SC-8 Existing run-metrics behaviour is unchanged | `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent/test_agent_runs.py tests/api/agent/test_agent_run_steps_wiring.py -q` | 0 | run 2026-09-12 at 5cfe366 | SC-8 |
| SC-9 No import path leads from the feedback service or router to the memory | `cd apps/api && ../../.venv/bin/python -m pytest tests/architecture/test_feedback_no_memory_edge.py -q` | 0 | run 2026-09-12 at 5cfe366 | SC-9 |
| SC-10 The SSE parser accepts assistant_message_id / agent_run_id on don | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/lib/stream/parseSSE.test.ts` | 0 | run 2026-09-12 at 5cfe366 | SC-10 |
| SC-11 Feedback controls render only for complete assistant messages with a s | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/components/chat/MessageFeedback.test.tsx src/components/chat/MessageList.render.test.tsx` | 0 | run 2026-09-12 at 5cfe366 | SC-11 |
| SC-12 Every new UI string exists in both locales | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm test src/messages.parity.test.ts` | 0 | run 2026-09-12 at 5cfe366 | SC-12 |
| SC-13 Frontend type-checks against the regenerated schema | `cd apps/web && PATH="$HOME/.nvm/versions/node/v24.17.0/bin:$PATH" pnpm exec tsc --noEmit` | 0 | run 2026-09-12 at 5cfe366 | SC-13 |
| SC-14 Backend lint is clean | `cd apps/api && ../../.venv/bin/ruff check app` | 0 | run 2026-09-12 at 5cfe366 | SC-14 |

### Not auto-verified

- **Postgres** — reached truth, not a Verify row (over the 60 s limit): the full backend suite on
  Postgres 17 / Python 3.12 at `5afa5d8` (isolated compose project `apitest`, worktree mounted into the
  cached test image, `alembic upgrade head` first, `tests/core/test_languages.py` excluded for its
  known container-layout issue) — 2538 passed, 0 failed.
- **End-to-end feedback flow** — reached traceability only. `playwright/chat-feedback.spec.ts` is
  collectable (SC-15) but was not executed: no `E2E_USER_*` credentials locally, and CI's web-e2e
  backend runs with an empty `OPENAI_API_KEY`, so every CI chat turn takes the failure path and is
  correctly not rateable. The spec skips unless `E2E_CHAT_LLM=1`.
- **Browser UAT** — not performed. The feedback row's look and the dialog's layout at phone width are
  unverified by any screenshot.
- **Vietnamese copy** — traceability only: the parity test proves every key exists in both locales,
  never that the translations read well.
- **Alembic head** — `d4f7a2c9e1b3` at `5afa5d8` (provenance). A long-lived database behind this
  head fails every feedback write; `alembic upgrade head` must run on deploy.
- **Generated OpenAPI types** — produced offline from `app.openapi()` at `bce70d8`; not byte-compared
  against a live `pnpm gen:api` run against this branch.
- **Langfuse score export and `agent_runs.trace_id`** — deferred by scope decision (UI + API only);
  the `export_hook` seam is a no-op.

### Rollback

- Remove `specs/user-feedback-v1/`; no application data or runtime behavior changed.
- Implementation commits (wave by wave, newest first) are listed under `### Verify` as they land;
  `git revert <sha>` each. The migration `d4f7a2c9e1b3` is additive (one nullable column + one new
  table); `cd apps/api && alembic downgrade b8e4c1f7a305` drops it.

### Harness-Delta

- backlog — **`hooks/lib/lane.sh` picks the first lexical `specs/*/PLAN.md` with `status: active`.**
  `specs/gh-193-booking-revise-idempotency/PLAN.md` was merged (PR #195) but left `active`, sorts
  before `user-feedback-v1`, and made risk-corroboration read gh-193's `Lane: normal` against this
  branch's migration diff, denying the wave-1 commit. The auto-mode classifier also refused a
  one-line `status: shipped` edit to that plan from this session. Workaround used: stage this
  SUMMARY (the hook reads a staged SUMMARY first). Fix belongs in `finishing-a-development-branch`
  (flip `status:` on merge) or in `lane.sh` (prefer the slug named in `specs/STATE.md`).
- backlog — **`branch-isolation-guard.sh` resolves the branch from `CLAUDE_PROJECT_DIR` (the main
  checkout), so inside an `EnterWorktree` worktree on a feature branch every Edit/Write is refused
  as "on shared branch main".** Worked around with Bash-written files.
- backlog — **The correctness FIND composition command in
  `.claude/skills/correctness-review/correctness-reviewer-prompt.md` uses `--fragment
  skills/correctness-review/...`, which only resolves in the harness repo's own layout.** In a
  consuming repo every form of that path fails with `prompt-compose: missing fragment` (tried
  `--root .claude`, `--root .`, no root). What works here: `--root . --fragment
  .claude/skills/correctness-review/prompts/shared.md --fragment
  .claude/skills/correctness-review/prompts/angles/<angle>.md`. The deployed prompt should carry the
  consumer-relative path, or the renderer should try `.claude/` when a bare `skills/` path misses.
- backlog — **`.claude/agents/PROJECT.md` → "Test execution" documents the harness repo, not
  travel-pi:** it names `bash scripts/run-tests.sh` (hook/script suites), which is absent (checked: test -e scripts/run-tests.sh at the worktree root) here.
  `finishing-a-development-branch` takes its suite command from that section, so a literal follow
  would run nothing useful. This run used `CLAUDE.md`'s commands instead (backend pytest suite, web
  `pnpm test`). PROJECT.md should be re-bootstrapped for this repo.
- note — `authorization` corroboration fired on the word `role` inside the `messages` column-set
  assertion in `tests/test_db_models.py` (false positive, see memory
  `risk-corroboration-session-auth-false-positive`). Lane is `high-risk` anyway, so no downgrade
  was needed.
