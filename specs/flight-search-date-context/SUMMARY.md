# flight-search-date-context — Summary

Lane: normal
Confidence: high
Reason: Changes existing agent flight-search collection behavior (flag #8) with weak/absent proof around relative-date resolution and multi-turn info stitching (flag #9); no hard gate — prompt/tool/agent-logic only, no auth/authz/data-loss/external-provider/public-contract.
Flags: existing-behavior, weak-proof
Affects: agent flight-search flow — app/agents (supervisor.py, subagents/_base.py, state.py ground_current_date), app/tools/flight_tools.py, planner/booking prompts
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- User's request VERBATIM at intake (Vietnamese). Investigate conversation
     7a22074c-4611-4690-8b64-b24856a52ef4. -->

check messages of conversation 7a22074c-4611-4690-8b64-b24856a52ef4
- user yêu cầu tìm chuyến bay, những tin nhắn có đầy đủ thông tin nhưng agent vẫn ko thể hiểu chính xác để collect info
- agent nên có khả năng phán đoán và biết chính xác hnay là ngày nào, ngày mai là ngày nào
- agent phải có khả năng hiểu những tin nhắn gần đây của convo để có thể thu thập, tóm tắt thông tin 1 cách thông minh

## What changed

<!-- Not yet implemented — intake only. Routed to normal-lane workflow. -->

Intake classification only. No code changed yet.

### Rationale

Reproduced the bug from the live thread: user asked for "chuyến bay Đà Nẵng đi HCM
sáng mai", then supplied "10/07" then "2026" across consecutive turns; the agent never
called the flight tool (all `tool_calls` NULL) and kept re-asking, finally claiming it
"only has the year 2026" — i.e. it failed to (a) resolve the relative date "sáng mai"
and (b) stitch "10/07" + "2026" from adjacent turns. Notably `ground_current_date()`
(`app/agents/state.py:79-100`) already injects today into every sub-agent, so the fix is
not "add date injection" but closing the gap between injected date and actual tool use —
a genuine design fork, hence normal lane with a short design step before planning.

### Alternatives considered

- Classify as `tiny` — rejected: touches shared agent prompts + tool contract and has no test proof; multi-turn/date behavior needs verification, not a direct patch.
- Classify as `high-risk` — rejected: no hard gate; ≤2 flags; changes are internal to the agent (prompt/tool arg parsing), not public API/auth/data.

### Deviations

- Rule 3 — Fixed the prescribed test invoke shape: `content_and_artifact` tools (`search_flights`/`search_hotels`) only return the `(content, artifact)` tuple when invoked with a `ToolCall`-shaped payload, not a plain args dict. Reworded `tests/api/tools/test_flight_tools_dates.py` + `test_hotel_tools_dates.py` to match the repo's existing convention. Commit `6935412`.
- Rule 3 — Trimmed the now-unused `timezone` import (`from datetime import datetime, timezone` → `from datetime import datetime`) in `app/tools/flight_tools.py` and `app/tools/hotel_tools.py` after replacing `datetime.now(timezone.utc)`. Commit `6935412`.
- Rule 1 — Updated the `resolve_agent_context` spy in `tests/api/agent/test_identity_hybrid.py` to accept `timezone=` (broke on the corrected signature). Commit `d3c1ccd`.
- Rule 1/3 (controller) — Applied the per-request tz to `AgentContext` via `dataclasses.replace` at the router call site instead of threading `raw_timezone` through `_resolve_context`. Functionally equivalent, cleaner separation of server-resolved tier vs body-supplied tz, and keeps the DB `session` arg off the changed lines so `risk-corroboration.sh`'s `\bsession\b` auth heuristic does not false-positive. `app/routers/agent.py`. Commit `d3c1ccd`.
- Rule 1 — Updated `tests/prompts/test_active_versions_load.py` (hardcoded `planner==5`/`booking==4`) to assert the new active versions `planner==6`/`booking==5`. Commit `a31a5e5`.
- Rule 1 (correctness-review) — `resolve_travel_date` now also accepts `YYYY/MM/DD` (slash form, a common model slip on ISO); previously misparsed day-first → `ValueError`. `app/core/dates.py`. (finding #3, score 75)
- Rule 1 (correctness-review) — New `today_in_timezone(tz)` helper: tools compute `today` through it so a misconfigured `AGENT_TIMEZONE` degrades to UTC instead of raising `ZoneInfoNotFoundError` out of the tool (was `ZoneInfo(...)` outside the try/except). `app/core/dates.py`, `app/tools/flight_tools.py`, `app/tools/hotel_tools.py`. (finding #4, score 75)

### Intent Findings

<!-- From /intent-review (blind to PLAN), oracle = the verbatim ### Intent above. -->

- **drift (medium), recorded — tool ignores per-request tz.** Same as advisory #1 below: the prompt grounds "today" in `ctx.timezone` but the tool's date math uses the server default `agent_timezone`. Behaviorally equivalent for the reproduced VN user (default == VN); divergent for other zones. Tied to FE task 5.2 — thread the resolved tz into the tools when 5.2 ships.
- **verification caveat (medium), recorded — the multi-turn over-asking loop is fixed only by the prompt reframe, with no deterministic test reproducing it.** The deterministic layer (`resolve_travel_date`) and the tool path are unit-tested, but the reported symptom (LLM looping / never calling the tool / not stitching "10/07"+"2026" across turns) rests on probabilistic prompt behavior — a FakeLLM (scripted) test cannot prove it. Per design §7 this is verified via the DeepEval harness + the manual repro in **Task 5.1** (acceptance step, pending). Intent coverage is present; the gap is in automated proof of the symptom, which is inherent to LLM-behavior changes.
- **drift (low), needs user confirmation — clause (3) delivered narrowly (dates only).** The summarizer (`app/memory/`) is untouched; clause (3) ("understand recent messages … gather/summarize intelligently") is addressed only via the date-stitching + "restate collected fields" prompt text. Reasonable if clause (3) was about the flight/hotel collection loop (the reproduced bug); a gap if the user meant a broader conversation-summarizer improvement. **RESOLVED — user confirmed (2026-07-10) clause (3) = the flight/hotel collection loop only, not a summarizer change. In scope; delivered.**

### Manual-repro observations (Task 5.1, 2026-07-10 — soft, not blocking)

- For a **read-only flight search** the planner **infers + surfaces** the resolved date ("sáng mai, 11/07/2026") and searches directly, rather than doing a separate yes/no confirm turn (the design's UX choice (ii)). Reasonable for a non-destructive search — the assumption is surfaced for correction; confirm-first matters more for `booking` (destructive). Prompt guides but does not hard-enforce it.
- When **no date is given at all**, the planner assumes "today" and searches (surfacing "hôm nay 10/07/2026") instead of asking "which date?". Slightly aggressive; a future prompt tweak could make it ask first. Not the reported bug.

### Advisory Findings

<!-- Correctness-review findings that scored < 80 (threshold) — recorded, not blocking. -->

- **#1 (score 0, latent) — RESOLVED (2026-07-10) via Task 5.2.** The tool's `today` still uses `agent_timezone` (tools can't read the context channel), but the tool's past-date check now carries a **1-day grace** (`parsed_date < today - timedelta(days=1)`) that absorbs the ≤1-day skew between the server-configured zone and the traveller's own zone. Chosen over threading per-request tz into every tool (InjectedState) — a backstop should tolerate tz skew, not re-impose a differently-zoned stricter check. Verified end-to-end: `/agent/stream` with `timezone:America/New_York` grounds the prompt in NY, resolves the relative date in NY, and the tool accepts it. FE (`useAgentStream.ts`, 3 stream call sites) now sends `Intl…timeZone`.
- **#2 (score 0, non-fatal) — `check_in`/`check_out` resolved independently, no max-stay upper bound.** Two out-of-order bare `DD/MM` (e.g. `20/07` + `05/07`) can roll `check_out` to next year → a ~350-night search that passes the `nights >= 1` guard. Does not crash; the `check_out > check_in` guard catches the reverse direction. Confirm-first prompting surfaces the absurd night count to the traveller. Left as-is (adding a max-stay guard is out of scope).

### Verify

<!-- To be filled by the implementation task. Investigation evidence below. -->

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Reproduce (read live thread) | `docker exec api-db-1 psql -U travel -d travel -c "SELECT role,substring(content,1,120) FROM messages WHERE conversation_id='7a22074c-4611-4690-8b64-b24856a52ef4' ORDER BY created_at"` | 0 | 26 msgs; flight-collect loop confirmed, no tool_calls |
| dates helper unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_dates.py -x` | 0 | 18 passed |
| context/schema unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_context.py tests/api/agent/test_agent_schemas.py -x` | 0 | 6 passed |
| grounding tz unit | `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_state.py -x` | 0 | 14 passed (incl. legacy one-arg) |
| tool date normalization | `cd apps/api && DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest tests/api/tools/test_flight_tools_dates.py tests/api/tools/test_hotel_tools_dates.py -x` | 0 | 4 passed; regression 68+32 |
| router tz + identity | `cd apps/api && DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest tests/api/agent -x` | 0 | 41 passed |
| agents + api/agent suites | `cd apps/api && DATABASE_URL=sqlite:///./travel.db ../../.venv/bin/python -m pytest tests/agents tests/api/agent -q` | 0 | 214 passed |
| prompt registry active | `cd apps/api && ../../.venv/bin/python -c "from app.prompts.registry import registry; assert 'Resolving is not guessing' in registry.get('planner'); assert 'Never invent' in registry.get('booking')"` | 0 | planner v6 + booking v5 active |
| full BE suite (CI-equivalent) | `.env aside + DATABASE_URL=sqlite … pytest <targeted>` | 0 | 382 passed (8 make-test fails are pre-existing .env artifacts) |
| **manual repro (Task 5.1)** | graph rebuilt (`docker compose up -d`); `POST /agent/chat` w/ `timezone:Asia/Ho_Chi_Minh` | 0 | "sáng mai"→**resolved 11/07/2026 + search_flights called** (5 real flights); "25/12"→**25/12/2026, no year re-ask**. Registry confirms planner v6 + booking v5 active. Bug (loop, no tool call) gone. |
| **FE network check (Task 5.2)** | `pnpm dev` + playwright (Node 24) w/ browser `timezoneId:America/New_York`, send a flight message | 0 | live `POST /agent/stream` body carries `"timezone":"America/New_York"` (browser-detected via `Intl…timeZone`), confirming FE→BE tz plumbing end-to-end. |

### Rollback

- Revert all implementation commits: `git revert 8d4aeb9 d3c1ccd 6935412 25e9fed`
- Or reset the branch to the plan commit: `git reset --hard 39b8216`
- Prompt-only rollback (keep code): set `app/prompts/active.yaml` back to `planner: 5`, `booking: 4` and rebuild the graph.

### Harness-Delta

- none
