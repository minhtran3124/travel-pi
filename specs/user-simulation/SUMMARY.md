# user-simulation — Summary

Lane: high-risk
Confidence: high
Reason: hard gates auth (HTTP path to /agent/* needs a JWT per test persona via CurrentUserDep) and external-provider (Claude Code CLI as a runtime driver; a 2D rendering library would enter a dependency manifest); also multi-domain BE harness + FE UI.
Flags: auth, external systems, multi-domain, data model, weak proof
Affects: apps/api/app/routers/agent.py (/agent/chat, /agent/stream consumer), apps/api/eval + evalkit (possible new dataset source), apps/web or a new standalone UI, dev/test database isolation
Input-type: new initiative
Route: brainstorming → xia2 (Deep) → writing-plans → using-git-worktrees → subagent-driven-development
Escalate: no (E001–E004 decided 2026-09-25: HTTP+JWT now, standalone UI, live, claude -p script + skill)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> tôi đnag có ý tưởng build giả lập môi trường cho chatbot travel.
> tức là sẽ tạo ra 1 môi trường có ng dùng ảo từ nhiều nơi, có kế hoạch du lịch, hỏi chatbot, ...
> nhưng có 1 vấn đề là tôi muốn tận dụng claude code quota thay cho việc chatbot dùng openai model
> hãy phân tích và tìm hiểu vấn đề này

(analysis turn concluded: the Claude Code quota drives the virtual users + grading; the chatbot stays on OpenAI as the system under test)

> ok, chạy feature-intake cho user-simulation đi
> notes: 1 cai toi muon nữa là sinh ra 1 simluate UI, kiểu làm ảnh 2D người di chuyển đến bàn chatbot rồi nói chuyện các kiểu bla bla ...

## What changed

Added a user-simulation environment for the travel chatbot. The sections below list what it contains, and the Verify table records the evidence for each part.

- **`apps/api/sim/`** — an orchestrator package, exposed as `python -m sim` and `make sim-run`:
  - `claude_cli` is the `claude -p` wrapper. It carries the quota gauge and runs on the subscription, never with `--bare`.
  - `keys` is a local RS256 JWKS server that signs tokens.
  - `sse` is the `/agent/stream` client.
  - `bus` fans events out over WebSocket, replays history to late clients, and serves the UI files.
  - `personas` generates travellers with tau-bench style rules.
  - `driver` holds the conversation loop, seat handling, resume, the quota guard, and error handling.
  - `grader` scores against a rubric and writes the reports and eval candidates.
  - `db_check` is a read-only snapshot of what each traveller left in the database.
- **Sim stack** — `docker-compose.sim.yml` runs `api-sim` on :8001 and `db-sim` on :5434, with JWKS pointed at the host. It has matching `sim-*` make targets.
- **`tools/sim-ui/`** — the live flat-isometric lobby (UI contract v1) and a Playwright smoke test that runs against the real bus.
- **Docs** — a README for the package and a `user-sim` launcher skill in the main checkout's `.claude/skills/`.

No file under `apps/api/app/` or `apps/web/` changed, and no dependency was added.

### Rationale

Splitting the two LLM roles keeps the chatbot's real model (gpt-5.4-mini, which prompts and eval baselines are tuned on) as the system under test, while the token-heavy persona role-play and grading run on the user's Claude Code quota, a legitimate personal use of Claude Code.

### Alternatives considered

- Swap the chatbot's LLM to Claude via the subscription — rejected: `claude -p` is not a tool-calling chat API (would need a subscription-backed proxy, a ToS grey zone), and it changes the system under test.
- Chatbot on Claude via `LLM_PROVIDER=anthropic` + API key — legitimate, but paid per token, not quota; kept as a model-comparison option only.

### Deviations

- Rule 3 — `api-sim` uses `env_file: [{path: .env, required: false}]` so `docker compose config -q` validates in a worktree without `apps/api/.env` (Task 1.7, 91fa966d). The missing-key case is caught by the sim preflight (Task 3.1).
- Rule 1 — The sim-UI chip correlates tool results by `id`, which led to a contract amendment: design §5.7 `bot_tool` now carries `id`, and the driver fills in `name` on results and `reply` on `bot_done` (Tasks 1.3 and 1.6, e163934a, 12f16b84).
- Rule 1 — Only a `rejected` rate-limit status counts as quota exhaustion; `allowed_warning` just updates the gauge. Design §5.1 was aligned to match (Task 1.1, 2fe04570, 3cb33dcf).
- Controller correction — The Task 1.6 dispatch note allowed Google Fonts, which contradicted the plan's "no CDN" rule. The links were removed and the plan won (3d5e4b0f).

- Plan gap — Wave 2 tasks depend on each other (2.2 imports `Persona` from 2.1; 2.3 imports `SessionResult` from 2.2), so they ran in order 2.1 → 2.2 → 2.3 instead of in parallel.
- Contract amendments during review:
  - design §5.7 `persona_leave` gains the `aborted` reason (401, 429, or tier-setup failure);
  - §5.9 says aborted travellers walk out at once with no badge;
  - `set_tier` is called per traveller as `set_tier(persona_id)`;
  - any `book_*` tool maps the session to the `booking` capability (a plan-owner decision recorded in PLAN Task 2.3).
- Recorded decision — One traveller's `set_tier` failure aborts the whole batch as `tier_misconfigured`. This is conservative: it prevents a storm of free-tier 429s. Sessions that already finished are kept.
- Task 3.3 — `.claude/` is excluded from git (`.git/info/exclude`), so the launcher skill lives in the main checkout's `.claude/skills/user-sim/` alongside every other repo skill and is not part of the PR diff.

Open Minor findings (forwarded to the final review):
- 1.5: two test helpers keep multi-parameter signatures on one line; `make_url` is parsed twice in `sim_session_factory`.
- 1.7: the `required: false` long syntax needs Docker Compose 2.24 or later (local 5.4.0).
- 1.2: the wrong-signature test reads the private `KeyServer._kid`.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| summary shape | `python .claude/scripts/verify_summary.py --lane user-simulation` | 0 | intake-time check | |
| claude_cli | `.venv/bin/python -m pytest apps/api/tests/sim/test_claude_cli.py -q` | 0 | 17 passed at 4bef4b72 | SC-1 |
| JWT round trip | `.venv/bin/python -m pytest apps/api/tests/sim/test_keys.py -q` | 0 | 3 passed | SC-2 |
| SSE mapping | `.venv/bin/python -m pytest apps/api/tests/sim/test_sse.py -q` | 0 | 7 passed | SC-3 |
| bus | `.venv/bin/python -m pytest apps/api/tests/sim/test_bus.py -q` | 0 | 4 passed | SC-4 |
| driver | `.venv/bin/python -m pytest apps/api/tests/sim/test_driver.py -q` | 0 | 14 passed | SC-5 |
| personas | `.venv/bin/python -m pytest apps/api/tests/sim/test_personas.py -q` | 0 | 8 passed | SC-6 |
| db_check | `.venv/bin/python -m pytest apps/api/tests/sim/test_db_check.py -q` | 0 | 3 passed | SC-7 |
| CLI preflight | `.venv/bin/python -m pytest apps/api/tests/sim/test_main.py -q` | 0 | 7 passed | SC-8 |
| sim compose | `docker compose -f apps/api/docker-compose.sim.yml config -q` | 0 | | SC-9 |
| UI smoke | `$HOME/.nvm/versions/node/v24.17.0/bin/node tools/sim-ui/smoke.mjs` | 0 | SMOKE PASS | SC-10 |
| ruff check | `.venv/bin/ruff check apps/api/sim apps/api/tests/sim` | 0 | | SC-11 |
| grader | `.venv/bin/python -m pytest apps/api/tests/sim/test_grader.py -q` | 0 | 15 passed | SC-12 |
| ruff format | `.venv/bin/ruff format --check apps/api/sim apps/api/tests/sim` | 0 | 22 files | SC-13 |
| launcher skill | `.venv/bin/python -c "import pathlib,sys; t=pathlib.Path('/Users/minhtran/Documents/minhtran3124/developer/travel-pi/.claude/skills/user-sim/SKILL.md').read_text(); sys.exit(0 if t.startswith('---') and 'make sim-run' in t else 1)"` | 0 | | SC-14 |

### Live UAT (2026-09-26)

- **Run:** `make sim-up`, then `make sim-run N=2 PARALLEL=2`, from the worktree with `apps/api/.env` linked from the main checkout. Run dir `apps/api/sim/runs/20260926T031527Z/` (local, gitignored). Exit 0, about 6 min.
- **Stack:** every piece worked against the real services:
  - `claude -p` generated 2 personas, drove the traveller turns and graded the sessions;
  - locally signed JWTs were accepted by `api-sim`;
  - SSE streamed from the real chatbot (`gpt-5-2025-08-07`);
  - the live lobby updated through the bus and the quota gauge moved;
  - `db_check` confirmed the trips the chatbot said it created;
  - `report.md`, `report.json` and `candidates/` were written.
- **Cost:** 8 `claude -p` calls. Claude 5h utilization went from 23% to 27%. The chatbot used 334k tokens (180k cached), about $0.59.
- **Results:**
  - `mai-hanoi` (vi): **fail 2.5**. After `plan_approval` and resume, the booking sub-agent ran `search_hotels` three times and `search_flights` once in about 160 s without booking, then hit the 180 s simulator turn budget. Filed as issue #236.
  - `unknown-erik` (en): **warn 3.0**. The hotel price-cap negotiation ran to max_turns, and the replies stayed verbose for an impatient traveller.
- **Simulator fixes from the run (17bd1432):**
  - The empty interrupt reply was shown as a blank bubble and graded as a broken reply. It is now recorded as a `[plan approval requested]` marker, the grader is told about it, and the UI skips empty replies.
  - Departed travellers now park in separate slots past the exit, so labels and badges no longer overlap.
  - The EXIT sign moved clear of the door.
  - `batch_start` carries the run id, which is shown in the header.
- **Delta review:** the fixes above (17bd1432, 0b9decb9) had their own correctness and intent review. That review found three more problems, which 0b9decb9 fixed: an interrupt turn now records exactly one bot turn, the exit slots wrap into rows of 8, and an empty reply that is not an interrupt shows as `(empty reply)`. After the fix, tests/sim passed with 101 tests and the UI smoke passed.

### Correctness review (2026-09-25)

- **Finder angles:** six (enclosing-function, removed-behavior, call-site-impact, stack-defects, guard-completeness, prior-art) over fb824f69..7336a3c3.
- **Locations:** 21 after deduplication, each scored by an independent scorer. The threshold was 75.
- **Fixed from the fix loop (score 75 or above):**
  - A — a grader exception lost every report;
  - H — load() accepted duplicate persona ids;
  - L — a traveller who left while queued stayed stuck in the UI;
  - M — grading spent quota on sessions that never ran;
  - N — personas had no email or phone, so booking was impossible;
  - O — golden candidates used `suite: "sim"`, which the eval CLI cannot select;
  - Q — a blocking `claude --version` ran on the event loop;
  - S — the UI replaced running tool chips on any result;
  - U — SSE `reset` did not reach the UI.
- **Advisory, fixed because the change was small:** B (null rate-limit windows), E (report.json said fail for ungraded sessions), J (seat leak on a publish failure), K (malformed SSE payload), P (resume marker copied into candidates, now `hitl`), R (`--parallel` bounded to 1..6).
- **Commits:** 9b59a347, d93ab873, and f2e4d455, which fixed three P3 regressions the re-review found (a version-probe OSError, NaN scores, marker-only candidates).
- **Re-review:** all 15 fixed ids confirmed resolved; tests/sim 100 passed.

### Intent Findings

- 2026-09-25, intent review (fresh context, a different model from the implementers, blind to PLAN and the research brief) over fb824f69..a4f8f038 found no intent divergence. It checked every clause: virtual travellers with trip plans; the Claude Code quota driving the travellers and grading; the chatbot staying on OpenAI; the live 2D lobby; decisions D1–D6; and the non-goals (the diffs of `apps/api/app`, `apps/web` and the dependency manifests are empty).

### Advisory Findings

Below the threshold and not fixed; recorded for a human to act on:

- C (25) `claude_cli.py:153` — quota detection accepts only `rejected` and `error_rate*`/`error_usage_limit`. This is a deliberate design choice; revisit it if the real CLI shows other hard-stop statuses.
- D (50) `claude_cli.py:134` — spawn OSError other than FileNotFoundError/PermissionError, and stdout UnicodeDecodeError, bypass the driver's single retry. The session still ends as `driver_error`, and the grader path is now protected by the catch-all.
- F (50) `bus.py:63` — `stop()` does not drain client queues. With the default 30 s linger this is harmless.
- G (50) `driver.py:266` — `leave_started` guards only the terminal leave, so a publish failure on a quota or aborted leave could double-publish.
- I (50) `keys.py:92` — the token is minted once per session with a 1 h TTL; a session over an hour would 401 and abort the batch as `auth_misconfigured`. The worst case computed from the code is about 57 min. This is a JWT change, so it is Rule 4 and needs a human decision.
- T (0) `driver.py:347` — a traveller message that comes with `intent_done` is not sent. This follows design §5.6; revisit after the live run shows whether closing messages matter.

### Not auto-verified

- Claude subscription and headless usage terms — reached provenance. The help-center article was read first-hand during research on 2026-09-25 (the credit change is paused, so `claude -p` draws from plan limits), but the terms can change.
- The live end-to-end batch reached truth once, on 2026-09-26 (see `### Live UAT`). It is not a re-runnable Verify row, because it spends real Claude plan quota and OpenAI tokens.
- Grader quality (whether the rubric verdicts are sensible) reached traceability only: the prompt was reviewed, but it has not been run against real sessions.

### Rollback

- `git revert f1553879..HEAD`, or drop the unmerged branch `feat/user-simulation`. The change is additive and no `app/` code changed.
- `make sim-reset` removes the sim stack and its `pgdata-sim` volume.
- Delete the launcher skill with `rm -r /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.claude/skills/user-sim` (it is outside git).

### Harness-Delta

- none
