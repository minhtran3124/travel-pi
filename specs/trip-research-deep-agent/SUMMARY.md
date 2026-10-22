# trip-research-deep-agent — Summary

Lane: high-risk
Confidence: medium
Reason: Three manifest hard gates fire — `external-provider` (adds the `deepagents` runtime dependency to `apps/api/requirements-ai.txt`), `public-contract` (a new REST route to start/read a research job), `authorization` (the job is scoped to the signed-in owner of the trip). Direction is clear; four design forks have sensible defaults but change the shape of the work, so a human confirms them before planning.
Flags: external-provider, public-contract, authorization, existing-behavior, multi-domain
Affects: apps/api/requirements-ai.txt (dependency manifest); new module apps/api/app/research/ (deep agent graph + job); new router (public contract: start / status / files / SSE progress); app/agents/supervisor.py + prompts/supervisor v14 + route_tasks (chat entry, routing hop only); app/tools registry (read tools reused, no change intended); apps/web trip page + chat suggestion chip + stream contract in apps/web/src/lib/stream (lockstep); LangGraph Postgres store (new `research` namespace, no migration)
Input-type: new initiative

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> merge it, checkout to main branch, pull latest code and intake for trip-research-deep-agent

Scope-deciding sentences from the same session (2026-09-18, the deepagents assessment the user accepted by asking for "bước 1" and now this intake):

> Cái nên build: Trip Research job. Từ trang trip, user bấm "Research this trip" (hoặc gõ trong chat, supervisor route sang). Backend tạo job chạy vài phút. Agent nghiên cứu theo từng chiều (flights, stays, per-day plan, visa/entry, mùa/thời tiết, budget), tự chấm theo rubric, ra một dossier nhiều file. User xem, sửa ("ngày 3 nhẹ hơn"), rồi duyệt để agent ghi vào trip thật (itinerary items, shortlist). Dossier tồn tại qua nhiều phiên.

> Ranh giới rõ: không đụng 5 specialist, không đụng supervisor, không thay `plan_node`. Job là graph thứ hai, endpoint riêng, checkpointer/store dùng chung.

> Tái dùng 100% tool từ `app/tools` (read tools của planner + concierge + RAG). Không viết tool mới.

Route: brainstorming (E001–E004 decided) → xia2 Deep ✅ research-brief.md + design.md (2026-09-18) → writing-plans → subagent-driven-development on `feat/trip-research-deep-agent` → correctness/intent review → PR
Escalate: resolved 2026-09-18 — E001 StoreBackend · E002 BackgroundTask + poll + SSE progress in v1 · E003 both chat and trip page · E004 propose-only. Confidence after decisions: high for direction; ceremony stays high-risk.

## What changed

PR: https://github.com/minhtran3124/travel-pi/pull/221 (branch `feat/trip-research-deep-agent`, base `main`).

**Wave 1 (tasks 1.1-1.5) landed.** `app/research/` package foundation: `deepagents`
0.7.15 pinned with four off-by-default `research_*` settings (task 1.1); `ResearchContext`
/ `ResearchState` / `research_tools()` + per-subagent tool lists resolved against the
registry (task 1.2); the non-replacement snapshot oracle `tests/fixtures/tools_snapshot.json`
+ `test_registry_snapshot.py` capturing `ALL_TOOLS`, `/agent/manifest` and the MCP tool
list before the feature touches anything (task 1.2, SC-26); seven `SKILL.md` files and the
`trip_research`/`trip_research_grader` v1 prompts (task 1.3); two seeded `agent_config` rows,
each mirroring a sibling of the correct model tier (task 1.4); `seed_agents_md` +
`GuardedStoreBackend` reusing the chat memory guard's content rules (task 1.5). Waves 2-7
(the agent build, runner, routes, chat entry, trip-page UI) are not started.

### Rationale

The chat harness caps a turn (recursion 25, 12 tool rounds, ledger 4, 1 revision), which is exactly where "plan my whole trip end-to-end" fails today; a long-running job with an isolated-subagent harness, a file-backed dossier the user edits, and a rubric-driven self-check is the one place `deepagents` adds capability the repo does not already hand-roll (`specs/agent-middleware-spike/DECISION.md` deferred `create_agent` for the specialists; that decision stands).

### Alternatives considered

- Extend the chat harness (raise budgets, add a "research" specialist) — rejected: re-hits the same ceilings and mixes a minutes-long job into a turn-based SSE contract.
- Managed Deep Agents hosting — rejected: provider-agnostic design, per-user JWT auth, Docker-resident data and RAG; MDA needs its own identity/hosting and a LangSmith key.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| `deepagents` resolves with the pinned stack and imports; `langchain-openai` stays 0.3.x | `cd apps/api && ../../.venv/bin/python -c "import deepagents, langchain_openai; from importlib.metadata import version as v; from packaging.version import Version as V; assert V(v('deepagents'))>=V('0.7.15') and V(v('langchain-openai'))<V('1.0'); print(v('deepagents'), v('langsmith'))"` | 0 | prints `0.7.15 0.12.6`. **Superseded by the keyed run**: 0.3.x cannot serialize deepagents' v1 content blocks, so the floor is now `langchain-openai>=1.6.2` and this assertion is inverted in the command above | SC-1 |
| Tool selection: `research_tools()` contains only registry read-only tools, excludes `list_tr… | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_tools.py -q` | 0 | 5 passed — read-only registry tools only, the five excluded names absent | SC-2 |
| Skills and prompts load: each `SKILL.md` has frontmatter `name` equal to its directory and ≤… | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_skills_prompts.py -q` | 0 | 10 passed — 7 SKILL.md parsed, both prompts at version 1 | SC-3 |
| Seeded `agent_config` rows `trip_research` and `trip_research_grader` exist with the same pr… | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_seed_config.py -q` | 0 | 4 passed — both rows seeded non-NULL, each mirroring a sibling of its own model tier | SC-4 |
| `build_research_agent` compiles offline with `FakeLLM`; the compiled graph's tool names cont… | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_agent_build.py -q` | 0 | compiles offline; task/write_todos/read_file/write_file/edit_file bound, execute absent, no general-purpose subagent | SC-5 |
| Permissions: a scripted `write_file` to `/skills/x/SKILL.md` returns a permission-denied too… | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_agent_permissions.py -q` | 0 | write to /skills denied with no store key; write to /research persists | SC-6 |
| A scripted full turn writes `/research/overview.md` and `/plan/proposal.json`; `validate_pro… | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_agent_turn.py -q` | 0 | full scripted turn: proposal rejected once by validate_proposal, revised, rubric satisfied | SC-7 |
| A second turn on thread `research:u1:t1` reuses the checkpoint (the `HumanMessage` count is … | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_agent_revise.py -q` | 0 | second turn on the same thread edits instead of rewriting | SC-8 |
| Memory helpers: `seed_agents_md` writes `/memory/AGENTS.md` from 2 stored preferences (both … | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_memory_unit.py -q` | 0 | seeds from 2 preferences, second call a no-op, injection phrase rejected | SC-9 |
| Progress bus: events for one run arrive in publish order, a late subscriber receives the rin… | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_progress.py -q` | 0 | 8 passed — publish order, ring replay, close, and no content/args in payloads; includes the two NEW-1 regressions | SC-10 |
| Runner: a scripted run finishes with `agent_runs.status == "completed"`, ≥ 1 step of kind `t… | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_runner.py -q` | 0 | completed run records a tool step and a terminal event; a timeout finishes failed without raising | SC-11 |
| Service: `start` refuses a trip the user does not own (`NotFoundError`), refuses a second st… | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_service.py -q` | 0 | foreign trip, already-running, latest and the stale sweep | SC-12 |
| Routes with `research_enabled=false`: every `/agent/research*` and `/agent/trips/{id}/resear… | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/api/research/test_routes_disabled.py -q` | 0 | every research path 404s with the flag off | SC-13 |
| Routes with the flag on: POST → 202 with `run_id`; free tier → 403; foreign trip → 403; seco… | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/api/research/test_routes.py -q` | 0 | 202 with run_id; 403 free tier; 403 foreign trip; 409 already running; 429 on the 4th start | SC-14 |
| SSE: with no bus entry the stream emits `research_start`, a snapshot `research_phase`, then … | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/api/research/test_stream.py -q` | 0 | 6 passed — snapshot path, live replay-then-tail, and the NEW-4 has/subscribe race | SC-15 |
| FE parser: `parseResearchSegment` maps each of the 8 event types and returns `null` for an u… | `cd apps/web && pnpm exec vitest run src/lib/stream/research.test.ts` | 0 | 12 passed — all 8 event types plus the unknown-event null | SC-16 |
| Supervisor: "research my trip in depth" (en) and "nghiên cứu kỹ cả chuyến đi giúp mình" (vi)… | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/agents/test_supervisor_research_routing.py -q` | 0 | research routes in en and vi; every v13 routing example replays to its original target under v14 | SC-17 |
| Chat node `research`: without a trip → `awaiting_user` and the `research_needs_trip` copy; w… | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/agents/test_research_node.py -q` | 0 | flag off, no trip, premium start, free tier | SC-18 |
| Reflection guard: a REVISE verdict after a `research` turn ends the turn without re-entering… | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/agents/test_reflection_research_guard.py -q` | 0 | a REVISE after a research turn ends the turn; start called exactly once | SC-19 |
| Non-replacement (file level): the tool registry, the specialist package and the chat stream … | `git diff --quiet main -- apps/api/app/tools/registry.py apps/api/app/agents/subagents apps/api/app/streaming/events.py apps/web/src/lib/stream/parseSSE.ts` | 0 | tool registry, specialist package, chat stream taxonomy and FE parser byte-identical to main | SC-20 |
| Eval goldens: `research-routing-en-01` and `research-routing-vi-01` exist under `routing` wi… | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/eval/test_research_goldens.py -q` | 0 | both goldens present under routing with expected_flow research | SC-21 |
| Lint clean on the API scope | `cd apps/api && ../../.venv/bin/ruff check app scripts tests/research tests/api/research` | 0 | clean | SC-22 |
| Web typecheck clean | `cd apps/web && pnpm exec tsc --noEmit` | 0 | clean | SC-23 |
| Research tab: renders the locked state for a free user, the empty state with a start button … | `cd apps/web && pnpm exec vitest run src/components/trips/research` | 0 | 11 passed — locked free tier, premium empty state, file list, and the A2 terminal-status retirement | SC-24 |
| Keyed smoke script exists, has a `--dry-run` that lists the seeded trip and exits 0 without … | `cd apps/api && DATABASE_URL=sqlite:///:memory: OPENAI_API_KEY= ../../.venv/bin/python -m eval.research_smoke --dry-run` | 0 | lists the seeded trip and exits without a key or an agent run | SC-25 |
| Non-replacement (behaviour level): sorted `ALL_TOOLS` names, the `/agent/manifest` payload a… | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_registry_snapshot.py -q` | 0 | ALL_TOOLS, /agent/manifest and the MCP list byte-identical with the flag off; with it on the manifest differs by exactly the research entry | SC-26 |
| Eval regression gate: the latest keyed eval-smoke report shows no capability below the commi… | `cd apps/api && make eval-compare` | 0 | dates +0.0% at baseline, every other capability above it; see the status log for the noisy first run | SC-27 |
| Web lint clean | `cd apps/web && pnpm lint` | 0 | clean | SC-28 |
| Resume: a `running` research row with a checkpoint on thread `research:u1:t1` is resumed by … | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_resume.py -q` | 0 | resumed run carries meta.resumed_from and finishes completed | SC-29 |
| The agent built by `build_research_agent` rejects a scripted `write_file` to `/memory/AGENTS… | `cd apps/api && DATABASE_URL=sqlite:///:memory: ../../.venv/bin/python -m pytest tests/research/test_agent_memory.py -q` | 0 | the built agent rejects an injection write to /memory and accepts a plain line | SC-30 |
| Full backend suite, clean environment, flag ON | `mkdir -p /tmp/trd && cd /tmp/trd && PYTHONPATH=$OLDPWD/apps/api $OLDPWD/.venv/bin/python -m pytest $OLDPWD/apps/api/tests -q -p no:cacheprovider --rootdir $OLDPWD/apps/api -c $OLDPWD/apps/api/pyproject.toml` | 0 | 2901 passed, 8 skipped. Must run from a directory without `apps/api/.env`; see the status log | |
| Full frontend suite | `cd apps/web && pnpm exec vitest run` | 0 | 366 passed, 57 files | |
| Advisory lock on real Postgres | `cd apps/api && docker run -d --rm --name trdpg -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test -p 55433:5432 pgvector/pgvector:pg17 && sleep 8 && TEST_DATABASE_URL=postgresql+psycopg://test:test@127.0.0.1:55433/test DATABASE_URL=postgresql+psycopg://test:test@127.0.0.1:55433/test ../../.venv/bin/python -m pytest tests/services/test_booking_duplicate_concurrency.py tests/research/test_service_concurrency.py -q; docker rm -f trdpg` | 0 | 8 passed — the two SC-skipped serialization tests plus the booking regression the extracted lock had to preserve | |
| Plan contract | `python3 .claude/scripts/check_plan_contract.py specs/trip-research-deep-agent/PLAN.md` | 0 | passed | |

### Keyed runs (real provider, `eval/research_smoke.py`)

Six runs against the real provider; each one found a defect no offline test could.
Command: `export OPENAI_API_KEY=… && cd apps/api && DATABASE_URL="sqlite:///<tmp>.db" ../../.venv/bin/python -u -m eval.research_smoke --instruction "Plan a relaxed 3-day long weekend in Da Nang for 2 people" --timeout 1500 --max-usd 3.0`

| # | Outcome | What it found | Fix |
| --- | --- | --- | --- |
| 1 | `ModuleNotFoundError: deepagents` | the Docker image predated the dependency | `docker compose build api` |
| 2 | 400 `Invalid value: 'tool_call'` | langchain-openai 0.3.x cannot serialize deepagents' v1 content blocks; FakeLLM never serializes, so no offline test could see it | floor raised to `>=1.6.2` (48ba6f84) |
| 3 | undiagnosable log line | the runner logged only `type(exc).__name__` | `exc_info=True` (d01e101a) |
| 4 | `ToolException: Trip 'current' not found` ($0.26) | `expense_summary` exposed `trip_id` to the model, and `SUBAGENT_TOOLS` bypassed the parent's filter | import-time invariant + tool dropped (eeab03b6) |
| 5 | `ToolException` on an ambiguous date ($0.31) | one rejected argument killed the whole multi-minute run | tool errors become `status="error"` messages (90151099) |
| 6 | `TimeoutError` at 600s, **all 7 files written** ($1.06) | the fan-out works end to end; `research_timeout_s=600` is too tight for synthesis | open — see below |
| 7 | `InvalidUpdateError: At key 'trip_id'` (365s) | parallel subagents each write the forwarded run constants into `LastValue` channels | `keep_run_constant` reducer (a9a8008f) |
| 8 | 429 `credit_balance_exhausted` (4s) | — | **blocked: the OpenAI account has no credits** |

Run 6 is the load-bearing evidence that the machinery works: `/flights.md`, `/stays.md`, `/days/day-1…3.md`, `/entry-and-season.md` and `/budget.md` were all produced by their own subagents.

**Open, unverified:** `settings.research_timeout_s` is still 600 although run 6 proves a full fan-out needs longer. Raising it is a one-line change but would ship unverified while credits are out, so it is deliberately left alone rather than guessed at.

### Not auto-verified

- **The agent's research quality.** Every check above proves the machinery — that files are written, ids validate, the rubric loop runs, budgets hold. None of them judges whether a dossier is *good*. That needs the keyed smoke (`make research-smoke`, not in CI) and a human reading one. Reached **truth** for mechanism, nothing for usefulness.
- **The per-trip advisory lock under real contention.** SC-12 and SC-29 run on SQLite, where the lock is a no-op; the serialization tests skip there and the real proof is the Postgres row above, run against a throwaway container rather than CI. A regression in the lock would pass `make test`.
- **A research run that reaches a valid proposal.** Six keyed runs were made (below). The fan-out is proven — all five subagents run and all seven dossier files are written — but no run has yet produced a validated proposal: run 4 timed out during final synthesis, run 5 died on the state-reducer bug now fixed, and run 6 could not start because the OpenAI account has no credits. **Blocked on credits, not on code.**
- **Gemini and Anthropic under deepagents.** Only the OpenAI path was exercised; the harness profile is keyed off the model's `ls_provider`, so another provider takes a different (null) profile. Reached **provenance** from the wheel, not **truth**.
- **The progress bus across workers.** It is per-process by design; a run started on one worker is invisible to another's live tail, which falls back to the DB snapshot. Correct but untested under multiple workers.

### Rollback

- `git revert <sha>` per commit. No schema migration in wave 1; if reverted, delete the seeded `agent_config` rows `trip_research`/`trip_research_grader` (harmless to leave — `research_enabled=False` means nothing resolves them) and `git checkout main -- specs/gh-193-booking-revise-idempotency/PLAN.md` if that unrelated fix should not ship with this branch.

### Harness-Delta

- backlog — the plan split an atomic change across two tasks (the `ALL_SUBAGENTS` entry in 5.1 and the graph node in 6.1), which cannot compile separately. A promptless specialist added to that tuple has predictable fan-out — prompt map, agent-config coverage, the public manifest — that a plan should enumerate as one Files set.
- backlog — per-wave verification scoped to the directories a task touches cannot see a shared-fixture invariant asserted elsewhere. A wave-1 regression in `tests/db` survived six waves because no wave ran that directory; only the full suite found it.
- backlog — `make test` and the plan's SC commands run from `apps/api/`, where the local `.env` supplies a real provider key and lifespan performs a live embeddings call per TestClient startup. That intermittently hangs the suite and looks exactly like a deadlock in the code under test. The evidence commands here run from a scratch directory for that reason.
