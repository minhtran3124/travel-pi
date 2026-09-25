---
slug: user-simulation
doc: design
created: 2026-09-25
status: approved
depends_on: SUMMARY.md, ESCALATIONS.md (E001 HTTP + JWT · E002 standalone UI · E003 live · E004 claude -p + skill)
---

# Design — user-simulation

File paths are relative to the repo root unless noted.

## 1. Purpose

Build a simulated environment in which virtual travellers from many places, each with their own
trip plan, talk to the travel chatbot. Every batch produces four outputs:

1. **Findings.** A graded report that lists broken sessions, wrong tool use, fabricated answers,
   and wrong reply language.
2. **Live visual.** A 2D lobby. Travellers walk to the chatbot desk and talk in speech bubbles.
3. **Eval candidates.** Sessions exported in the evalkit golden shape, which a human reviews
   before promoting them.
4. **Sample data.** The trips, bookings, and expenses the travellers create, which stay in the
   simulation database.

**Two LLM roles, two budgets.** The chatbot is the system under test and keeps its real
configuration (OpenAI, `gpt-5.4-mini`), because prompts and eval baselines are tuned on that
model. The travellers and the grader run on the user's **Claude Code subscription quota** through
`claude -p`. Replacing the chatbot's model with the subscription was considered and rejected (see
SUMMARY.md, Alternatives).

## 2. Decisions already made

| # | Decision | Source |
|---|---|---|
| D1 | Travellers call the chatbot over real HTTP, `POST /agent/stream` (SSE), with one JWT per traveller. | E001 |
| D2 | JWTs are RS256 tokens that the simulator signs itself. A local JWKS server publishes the public key. A dedicated `api-sim` instance points `SUPABASE_JWKS_URL` and `SUPABASE_JWT_ISSUER` at it. No change to `apps/api/app/core/auth.py`. | brainstorming |
| D3 | The UI is a standalone static page, `tools/sim-ui/index.html`, drawn with plain Canvas 2D. It uses no framework and adds no dependency. | E002 |
| D4 | The UI is live from v1. It subscribes to a local WebSocket while the batch runs. | E003 |
| D5 | Travellers and grading run through `claude -p` from a Python orchestrator, and a thin skill launches it. | E004 + approach 1 |
| D6 | Scale per batch: 5–10 travellers, 2–3 running concurrently, one desk with 2–3 seats and a queue. All counts are parameters. | brainstorming |

## 3. Non-goals (v1)

- Real Supabase users, and sample data that can be viewed through the web app login.
- Several chatbot desks, and batches larger than about 10 travellers.
- A replay mode in the UI. The transcript file is written so replay can be added cheaply later.
- Promoting sessions to goldens automatically. v1 writes candidates for human review.
- Any change under `apps/api/app/`, `apps/web/`, or to a dependency manifest.
- Load or performance testing.

## 4. Architecture

```
┌──────────── make sim-up ─────────────┐        ┌──── apps/api/sim/ (host, root .venv) ─────────┐
│ db-sim  (pgvector, host :5434)       │        │ keys.py     RS256 keypair + JWKS server :8766 │
│ api-sim (same image as api, :8001)   │◀─HTTP──│ personas.py generate N travellers (claude -p) │
│  SUPABASE_JWKS_URL=host:8766/jwks    │  SSE   │ driver.py   turn loop: claude -p → /stream    │
│  SUPABASE_JWT_ISSUER=sim             │        │ bus.py      event bus → WebSocket :8765       │
│  OPENAI_API_KEY from apps/api/.env   │        │ grader.py   claude -p rubric + db_check       │
└──────────────────────────────────────┘        │ runs/<ts>/  transcript.jsonl, report.{json,md}│
                                                └───────────────┬───────────────────────────────┘
                                                                │ ws://localhost:8765
                                                tools/sim-ui/index.html (Canvas 2D, served by bus)
```

The orchestrator lives next to `apps/api/eval/`, so it can import `evalkit` and the eval adapters
(the golden dataset loader). It runs on the host from the root `.venv`. `api-sim`
runs in Docker.

## 5. Components

Each unit has one purpose and a narrow interface. Every unit that calls `claude` does so through
one wrapper, `claude_cli.py`, so tests can swap in a fake.

### 5.1 `apps/api/sim/claude_cli.py` — the only caller of `claude -p`

- `run(system_prompt: str, user_prompt: str, schema: dict, model: str | None) -> dict`
- It spawns `claude -p` in a fresh temporary directory with these flags:
  - `--system-prompt`
  - `--model ${SIM_CLAUDE_MODEL:-sonnet}`. Without `--model` the CLI uses the user's default, which is Opus.
  - `--tools ""`, `--disable-slash-commands`, `--strict-mcp-config`, `--no-session-persistence`
  - `--setting-sources ""`, which keeps OAuth and drops user hooks and plugins
  - `--output-format stream-json --verbose --json-schema <schema>`
- It reads the stream line by line. The final `result` event carries `structured_output`. The `rate_limit_event` carries `five_hour` and `seven_day` utilization, which the wrapper exposes as `last_quota: {five_hour, seven_day, resets_at}`. Verified in research-brief.md.
- It must **not** pass `--bare`. `--bare` skips OAuth and reads only `ANTHROPIC_API_KEY`, which
  would move the cost from the subscription to the API.
- It returns the parsed `structured_output`. A process timeout defaults to 120 s. The parser tolerates both output shapes: a JSON array of events and a single object.
- It records `claude --version` once per batch in the report.
- Error mapping:
  - A usage or rate limit becomes `QuotaExhausted`: either an `is_error` result with a rate-limit status, or a `rate_limit_event` whose status is `rejected`. Warning statuses such as `allowed_warning` are not exhaustion; they only update the gauge.
  - Output that fails the schema, or an unexpected exit, becomes `DriverError`.
  - A timeout also becomes `DriverError`.

### 5.2 `apps/api/sim/personas.py` — travellers

- `generate(n: int, seed: int | None) -> list[Persona]` runs one `claude_cli.run` with a schema for
  a list of personas, then writes `runs/<ts>/personas.json`.
- `load(path) -> list[Persona]` re-runs an earlier cast exactly (`--personas <file>`).
- `Persona` (pydantic) has these fields:
  - `id`: a short slug.
  - `name`, `home_city`, `country_code`.
  - `language`: a BCP-47 code; the cast mixes `vi`, `en`, and others.
  - `budget`: an amount and a currency.
  - `trip_goal`: destination, date window (possibly vague), party size, and interests.
  - `style`: terse, chatty, changes their mind, or impatient.
  - `will_book: bool`.
  - `max_turns`: 4–8.
- The per-turn traveller prompt follows the tau-bench user-simulator rules:
  - send one message per turn;
  - reveal facts gradually;
  - never invent facts that are not in the persona card;
  - write in the persona's language;
  - set `intent_done` only when the goal is met or clearly impossible.
- The generator prompt asks for variety across origin, language, and style. It also asks for a
  few travellers who leave out key facts (origin or dates), which exercises the chatbot's
  never-assume-the-departure-point rule.

### 5.3 `apps/api/sim/keys.py` — local identity provider

- On start it generates an in-memory RS256 keypair with a fresh `kid` for each batch. `api-sim` caches one `PyJWKClient` per URL (`app/core/auth.py:25`). An unknown `kid` makes PyJWT fetch the JWKS again, so a new keypair per batch works without restarting `api-sim`.
- It serves `GET /.well-known/jwks.json` on `:8766`, using the stdlib `http.server` in a
  background thread.
- `token_for(persona_id) -> str` signs `sub=sim-<persona_id>`, `aud=authenticated`, `iss=sim`,
  and `exp` one hour ahead.
- The keypair is regenerated every batch. Tokens are never written to disk.

### 5.4 `apps/api/docker-compose.sim.yml` and `make` targets

The targets live in `apps/api/Makefile`. The root `Makefile` gets thin delegating targets with the same names, as it does for `eval-*`, so `make sim-up` works from either directory.

- `db-sim`: `pgvector/pgvector:pg17`, with user, password, and database all `travel` (the same as dev), host port `5434`, named volume `pgdata-sim`. The Compose
  project name is `travel-sim`, so it never shares or tears down the dev stack. See memory
  `docker-test-compose-shares-project-name`.
- `api-sim`: `build: .`, `env_file: .env`, with these overrides:
  - `DATABASE_URL` pointing at `db-sim`.
  - `SUPABASE_JWKS_URL=http://host.docker.internal:8766/.well-known/jwks.json`.
  - `SUPABASE_JWT_ISSUER=sim`.
  - `ENVIRONMENT=development`.
  - `WEB_SEARCH_ENABLED=false`. This is already the default (`config.py:85`); it is pinned so a `.env` value cannot turn it on. No other feature flag is set. The injection-screen flag exists only in open PR #231, and if it merges the flag is off by default.
  - Host port `8001`, no source bind mount, no `--reload`.
- `make sim-up`: brings the stack up and waits for `GET /healthz` on `:8001`. It adds no migrate or seed step, because the image entrypoint already runs `alembic upgrade head` (`docker/entrypoint.sh:7`) and the lifespan already runs `seed_all` (`app/core/lifespan.py:34`).
- `make sim-down`: stops the stack and keeps the volume. `make sim-reset` also removes the volume.
- `make sim-run N=8 PARALLEL=3 [PERSONAS=file] [SEED=n]`: runs the orchestrator.
- The orchestrator makes every simulated user premium before that traveller's first turn by running `docker compose -p travel-sim exec api-sim python -m scripts.set_tier sim-<id> premium`. `set_tier` upserts the user row (`scripts/set_tier.py:27`), and `ensure_user` leaves an existing row alone (`app/repositories/user.py:21-25`). No warm-up request is needed.

### 5.5 `apps/api/sim/sse.py` — stream client

- `stream_turn(base_url, token, body) -> AsyncIterator[SseEvent]` uses `httpx`.
- It parses the named events `start`, `token`, `reset`, `subagent`, `tool_call`, `tool_result`,
  `panel`, `interrupt`, `done`, and `error` (source: `app/streaming/events.py`).
- It is a pure parser plus transport, with no simulation logic.

### 5.6 `apps/api/sim/driver.py` — the conversation loop

- `run_batch(personas, parallel, base_url, bus) -> BatchResult` runs travellers under an
  `asyncio.Semaphore(parallel)`. A traveller waits in the queue until a seat frees up.
- **Quota guard.** Before admitting a traveller, the driver reads `claude_cli.last_quota`. If `five_hour` or `seven_day` is at or above `SIM_QUOTA_CEILING` (default 0.85), it stops admitting new travellers. Travellers in flight finish their current turn, and the batch ends as `quota`. Every `claude_cli` result updates the gauge, and the bus sends it to the UI header as a `quota` event.
- Each traveller runs a loop until the session ends:
  1. Call `claude_cli.run` with the traveller's system prompt (the persona card plus
     role-play rules) and the transcript so far. It returns
     `{message: str, intent_done: bool}`.
  2. If `intent_done` is true, the session ends.
  3. Otherwise send `POST /agent/stream` with `{message, conversation_id, timezone}`. The first
     turn sends no `conversation_id` and takes it from the `start` event.
  4. Forward each SSE event to the bus and append it to the transcript.
  5. On an `interrupt` event whose `payload.type == "plan_approval"` (the event is `{conversation_id, payload: {type, draft}}`; see `app/streaming/events.py:70` and `app/agents/nodes.py:367`), send a follow-up request with `{conversation_id, resume: {approved: persona.will_book}}`. The decision comes from the persona card and is fixed for the whole session, so the result is deterministic. The follow-up request is recorded as a turn.
- The loop also stops when `max_turns` is reached.
- There is a per-turn wall clock of 180 s, covering the whole stream plus any resume.
- The driver never retries a chatbot error. The error is the finding.

### 5.7 `apps/api/sim/bus.py` — events and the UI server

- It has one in-process async queue, fanned out to:
  - `runs/<ts>/transcript.jsonl`, one JSON event per line and always written;
  - every connected WebSocket client on `:8765`;
  - an in-memory history of the batch, replayed to any client that connects late or reconnects.
- The same port also serves the static `tools/sim-ui/` files over HTTP. It uses the `websockets` server's `process_request` hook: a request without a WebSocket upgrade is answered with the matching static file. `make sim-run` prints `http://localhost:8765/`.
- UI event contract. Every event has `{"t": <ms since batch start>, "type": ..., "persona_id": ...}`
  plus these fields:

| type | extra fields |
|---|---|
| `batch_start` | `personas: [{id, name, country_code, language}]`, `seats` |
| `persona_queue` | — |
| `walk_to_desk` | `seat` |
| `user_say` | `text` |
| `bot_subagent` | `name` |
| `bot_tool` | `id` (the tool-call id, correlates a result with its call), `name`, `status` (`running`/`ok`/`error`). The SSE mapper leaves `name` off result events; the driver fills it in from the matching `id`. |
| `bot_token` | `text` (the chunk) |
| `bot_done` | `reply` (the full text, assembled by the driver from the `bot_token` chunks), `usage` |
| `bot_reset` | — (the SSE `reset`; the UI clears the streaming bot bubble) |
| `bot_interrupt` | `kind` |
| `bot_error` | `code`, `message` |
| `persona_leave` | `reason` (`done`/`max_turns`/`bot_error`/`driver_error`/`quota`/`aborted`; `aborted` means the batch aborted (a 401, a 429, or a tier-setup failure) before this traveller finished) |
| `session_graded` | `score` (0–5), `verdict` (`pass`/`warn`/`fail`) |
| `quota` | `five_hour`, `seven_day` (0–1), `resets_at` |
| `batch_end` | `summary` |

- The contract is versioned by a `"v": 1` field on `batch_start`.

### 5.8 `apps/api/sim/grader.py` — findings and eval candidates

- `grade(session) -> Grade` runs one `claude_cli.run` per session with a fixed rubric. It scores:
  - goal completion;
  - fabrication, meaning claims not backed by a tool result in the transcript;
  - whether the reply language matches the traveller;
  - whether the chatbot asked instead of assuming a missing origin or date;
  - tool appropriateness;
  - tone.

  It returns per-criterion scores, evidence quotes, and a verdict.
- The grader's evidence is the transcript: the traveller and bot text, `tool_call` names and argument previews, and `panel` data. SSE `tool_result` carries only a status, so a fabrication finding is limited to claims that contradict or go beyond `panel` data. The report says this.
- `apps/api/sim/db_check.py` (read-only) opens a session on `db-sim` (`postgresql+psycopg://travel:travel@localhost:5434/travel`). For each traveller's user id `sim-<id>` it lists bookings and trips through the existing repositories (`BookingRepository.list_all`, and `TripRepository.list_trips`). The grader receives these rows and checks whether the bookings and trips the chatbot said it created really exist. `DbOracle` is not used: it recomputes ground truth for `flight_offers`, `hotel_availability`, `fx_rate`, and `trip_budget` (`eval/adapters/db_oracle.py:53`), and cannot look up rows a user created. Price checks and expense checks are out of scope for v1. `list_trips` returns only live trips, so the grader prompt treats a trip the chatbot created and then deleted as "deleted", not "fabricated". `db_check` counts only rows created after the batch started, so an earlier batch that re-used the same cast (`--personas`) cannot leak into this one.
- Outputs under `runs/<ts>/`:
  - `report.json`, which is machine-readable;
  - `report.md`, with a failing-first table and links to transcript line ranges;
  - `golden_candidates.json`, sessions with a `fail` or `warn` verdict converted to the evalkit
    golden shape. It is loaded through the eval dataset loader to prove the shape, and never
    written into `eval/datasets/`.

### 5.9 `tools/sim-ui/` — the 2D lobby

- `index.html` plus `sim.js` and `sim.css`, in plain ES modules with no build step and no CDN.
- Scene: an entrance on the left, a queue lane, and the chatbot desk on the right with `seats`
  chairs and a bot avatar per seat.
- Travellers are drawn as a circle with the country flag emoji, a name label, and a colour taken
  from their id.
- Animation:
  - `walk_to_desk` tweens the traveller from the queue to the seat.
  - `user_say` shows a bubble above the traveller.
  - `bot_token` streams text into the bot bubble.
  - `bot_tool` shows a tool icon above the bot (✈️ flights, 🏨 hotels, 💰 budget, 🌤️ weather,
    🔎 search, ⚙️ anything else).
  - `persona_leave` walks the traveller out with a ✅, ⚠️, or ❌ badge once
    `session_graded` arrives. A traveller that leaves with reason `aborted` is never graded, so it walks out at once with no badge.
- A side panel shows the full transcript of the traveller you click. A header shows batch
  progress (done/total) and the quota status.
- It auto-reconnects the WebSocket and rebuilds the scene from the replayed history.
- It works in both light and dark colour schemes.

### 5.10 `.claude/skills/user-sim/SKILL.md` — launcher

- It checks that the sim stack is up (or runs `make sim-up`), then runs
  `make sim-run N=… PARALLEL=…`, prints the UI URL, reads `report.md` when the batch ends, and
  summarises the findings.
- It holds no simulation logic.

## 6. Data flow of one turn

```
driver ──claude_cli.run(persona card, transcript)──▶ {message, intent_done}
   │ user_say → bus
   ├──POST /agent/stream (Bearer token_for(id))──▶ api-sim ──▶ supervisor → sub-agents → tools → db-sim
   │◀── SSE start/subagent/tool_call/token/panel/interrupt/done
   │ bot_* → bus  (bus → transcript.jsonl + WebSocket → UI)
   └─ interrupt(payload.type=plan_approval) → POST /agent/stream {conversation_id, resume:{approved: will_book}}
```

## 7. Error behaviour

| Situation | Behaviour | Status recorded |
|---|---|---|
| Quota utilization reaches `SIM_QUOTA_CEILING`, or the Claude Code usage or rate limit is hit | Admit no new travellers. Travellers in flight stop after their current turn. Write a partial report. Never retry in a loop. | `quota` |
| `claude -p` output fails the schema, or the process fails | Retry once. If it fails again, end that session. Other sessions continue. | `driver_error` |
| api-sim returns 4xx/5xx other than 401, sends an SSE `error`, or passes the 180 s turn clock | Record the error in the transcript and end the session. It counts as a chatbot finding in the report. | `bot_error` |
| 401 from api-sim | Abort the batch at once. Print a JWKS and issuer checklist. This is an environment error, not a finding. | batch `auth_misconfigured` |
| 429 from the daily turn quota | A premium-tier setup failure. Abort the batch with a hint to re-run tier setup. | batch `tier_misconfigured` |
| The UI is closed or disconnected | No effect on the run. The transcript is still written, and the UI rebuilds from history when it reconnects. | — |
| Preflight fails (no `claude` on PATH, stack down, `OPENAI_API_KEY` empty in `apps/api/.env`) | Fail before generating personas, so no quota is spent. | exit 2 |
| The base URL is not the sim port (8001) and `--i-know` is not passed | Refuse to run. This guards the dev database. | exit 2 |

## 8. Testing

These tests are offline and run inside `make test`. They use no real `claude` and no real OpenAI.
They live in `apps/api/tests/sim/`.

1. **JWT round trip.** A token from `keys.token_for` is accepted by the real
   `app/core/auth.py` verifier when settings point at the local JWKS server. A token signed by a
   different key is rejected. This is the load-bearing proof for D2. The test overrides `get_settings` (or clears its cache) and clears the cached `PyJWKClient`, so `.env` values cannot leak into it (memory `env-openai-key-test-breaks-llm-tests`).
2. **SSE parser.** A recorded event stream that contains every event type, including
   `interrupt` and `error`, maps to the expected transcript entries and UI events.
3. **Driver loop.** A fake `claude_cli` with scripted outputs and a fake API cover:
   - the session stops on `intent_done`;
   - the session stops on `max_turns`;
   - `resume.approved` follows `will_book`;
   - `QuotaExhausted` stops admission and marks in-flight sessions;
   - the semaphore never exceeds `parallel`.
4. **Grader output shape.** `golden_candidates.json` from a fixture session loads through the
   evalkit dataset loader.
5. **UI smoke.** A Node 24 `playwright-core` script opens `index.html` against a stub WebSocket
   that replays a fixture `transcript.jsonl` and takes a screenshot. This is a manual check,
   recorded in SUMMARY `### Verify`.
6. **Live smoke.** From the repo root, `make sim-up && make sim-run N=2 PARALLEL=2`, with the UI watched in a browser.
   This is manual and spends quota. It is recorded in SUMMARY `### Verify` with the report path.

## 9. Research results

All the items raised at design time were resolved on 2026-09-25. See `research-brief.md`.

- `claude -p` without `--bare` bills to the subscription (`apiKeySource: none`). The overhead is about 1k input tokens per call. `--setting-sources ""` works.
- `--json-schema` returns its result in `structured_output`.
- `api-sim` in Docker reaches the host JWKS through `host.docker.internal` on macOS.
- `httpx`, PyJWT, `cryptography`, and `websockets` are already installed.
- `set_tier` upserts the user row, so no warm-up request is needed.
- The Agent SDK credit change is paused, so `claude -p` draws from the shared plan limits. The quota guard (§5.6) exists for this reason.

## 10. Risks

- **Quota burn.** There is one `claude -p` call per turn, one per session for grading, and one per batch for generating personas. A batch of 8 travellers × 6 turns is about 57 calls. The defaults stay small, and the report
  shows the number of calls.
- **Persona realism.** A role-played traveller may be more cooperative than a real one. The style
  mix and the travellers who leave facts out are there to reduce this.
- **OpenAI spend on the chatbot side.** This is real money, though small with `gpt-5.4-mini` and
  caching. The report shows total `usage` from the `done` events.
- **Grader bias.** Claude grades an OpenAI chatbot. Findings are advisory. Candidates become
  goldens only after human review.
