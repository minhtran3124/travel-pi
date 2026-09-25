---
slug: user-simulation
status: active
owner: Minh Tran
created: 2026-09-25
---

# User simulation — virtual travellers on the Claude Code quota, live 2D lobby

Inputs: `design.md` (approved 2026-09-25, with research deltas applied) and `research-brief.md`.
Paths are relative to the repo root.

## 1. Motivation

We need a repeatable way to watch the travel chatbot handle many different travellers. Each
batch should produce findings, eval candidates, and sample data. Role-playing the travellers is
the token-heavy part, and it runs on the user's Claude Code subscription through `claude -p`.
The chatbot stays on its real OpenAI configuration and is called over real HTTP/SSE, with a
locally signed JWT for each traveller. A live 2D lobby shows travellers walking to the chatbot
desk and talking.

## 2. Non-goals

- No change under `apps/api/app/` or `apps/web/`, and no dependency-manifest change.
- No real Supabase users, no multi-desk lobby, no replay mode in the UI, and no automatic
  promotion into `apps/api/eval/datasets/`.
- No price or expense checks in `db_check`. No load testing.

## Global Constraints

- **Package layout.**
  - Python code lives in `apps/api/sim/` (package `sim`).
  - Tests live in `apps/api/tests/sim/`.
  - The UI lives in `tools/sim-ui/`.
  - Batch outputs go to `apps/api/sim/runs/<UTC-timestamp>/`, which is gitignored through a new
    entry in the root `.gitignore`.
- **`claude -p` flags.** Only `sim/claude_cli.py` spawns `claude`. It always passes
  `--system-prompt`, `--model ${SIM_CLAUDE_MODEL:-sonnet}`, `--tools ""`,
  `--disable-slash-commands`, `--strict-mcp-config`, `--no-session-persistence`,
  `--setting-sources ""`, and `--output-format stream-json --verbose --json-schema <schema>`.
  It runs with `cwd` set to a fresh `tempfile.mkdtemp()`. It never passes `--bare`: `--bare`
  bills `ANTHROPIC_API_KEY` instead of the subscription (research-brief).
- **Tests are offline.** No test spawns the real `claude`, calls OpenAI, or needs Docker.
  `claude` is replaced by a fake executable script under `apps/api/tests/sim/fixtures/`, found
  through `SIM_CLAUDE_BIN`. The API is replaced by an `httpx.MockTransport` or an in-process
  ASGI stub.
- **Test isolation.**
  - Tests that build `Settings` pass values explicitly or monkeypatch the environment. They
    never read `apps/api/.env` values (memory `env-openai-key-test-breaks-llm-tests`).
  - The JWT test clears `app.core.auth._jwks_clients` before and after it runs.
- **Identity.**
  - Traveller subject: `sim-<persona_id>`.
  - Token claims: `aud=authenticated`, `iss=sim`, `exp` one hour ahead.
  - Token header: RS256 with a fresh `kid` for each batch.
  - Tokens are never written to disk or logged.
- **Ports.**
  - `api-sim` on host `8001`
  - `db-sim` on host `5434`
  - JWKS on `8766`
  - bus (WebSocket and static UI) on `8765`
  - The Compose project name is always `travel-sim`.
- **Safety guard.** The orchestrator refuses a base URL whose port is not `8001` unless
  `--i-know` is passed. `db_check` connects only to port `5434`.
- **Quota guard.** A new traveller is admitted only while both `five_hour` and `seven_day`
  utilization are below `SIM_QUOTA_CEILING` (default `0.85`).
- **Style.** Signatures with more than one parameter put one parameter per line with a trailing
  comma. Keep comments minimal and do not restate the signature. `ruff check` and
  `ruff format --check` stay clean on `sim` and `tests/sim`.
- **UI.**
  - Plain ES modules, Canvas 2D. No build step, no CDN, no npm dependency.
  - Colours come from CSS custom properties, with a `prefers-color-scheme: dark` override.
- **UI event contract.** It follows design §5.7 exactly, including the `quota` event. Every
  event carries `t`, `type`, and `persona_id` (`null` for batch-level events). `batch_start`
  carries `"v": 1`.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | `claude_cli.run` returns `structured_output`, updates `last_quota` from `rate_limit_event`, raises `QuotaExhausted` on a rejected rate limit, never passes `--bare`, and passes `--setting-sources ""` | `.venv/bin/python -m pytest apps/api/tests/sim/test_claude_cli.py -q` | exit 0 |
| SC-2 | A token from `keys.token_for` passes the real `app.core.auth` verifier against the local JWKS, and a token signed by another key raises `AuthError` | `.venv/bin/python -m pytest apps/api/tests/sim/test_keys.py -q` | exit 0 |
| SC-3 | The SSE client maps a recorded stream with all 10 event names into the expected UI events, including `interrupt` with `payload.type == "plan_approval"` | `.venv/bin/python -m pytest apps/api/tests/sim/test_sse.py -q` | exit 0 |
| SC-4 | The bus writes every event to `transcript.jsonl`, fans it out to 2 WebSocket clients, replays history to a late client, and serves `index.html` over HTTP on the same port | `.venv/bin/python -m pytest apps/api/tests/sim/test_bus.py -q` | exit 0 |
| SC-5 | The driver stops on `intent_done` and on `max_turns`, sends `resume.approved == will_book` on `plan_approval`, never runs more than `parallel` travellers at once, stops admitting at the quota ceiling, and aborts the batch on 401 and 429 | `.venv/bin/python -m pytest apps/api/tests/sim/test_driver.py -q` | exit 0 |
| SC-6 | Persona generation validates against the `Persona` model, and `load()` round-trips `personas.json` | `.venv/bin/python -m pytest apps/api/tests/sim/test_personas.py -q` | exit 0 |
| SC-7 | `db_check` lists only the sim user's bookings and trips created after the batch start, and refuses a non-sim DB port | `.venv/bin/python -m pytest apps/api/tests/sim/test_db_check.py -q` | exit 0 |
| SC-8 | The CLI preflight exits 2 with no `claude` call when `claude` is missing, when the base URL port is not 8001 without `--i-know`, when `OPENAI_API_KEY` is empty, or when the base URL does not answer `/healthz` | `.venv/bin/python -m pytest apps/api/tests/sim/test_main.py -q` | exit 0 |
| SC-9 | The sim Compose file is valid, and its project name is `travel-sim` | `docker compose -f apps/api/docker-compose.sim.yml config -q` | exit 0 |
| SC-10 | The lobby UI loads from the bus with fixture history. After a roster row is clicked, `#done-count` reads `1/2` and `#transcript` has 4 or more `li` items | `$HOME/.nvm/versions/node/v24.17.0/bin/node tools/sim-ui/smoke.mjs` | exit 0 |
| SC-11 | The sim package and its tests are lint-clean | `.venv/bin/ruff check apps/api/sim apps/api/tests/sim` | exit 0 |
| SC-12 | The grader's `golden_candidates.json` loads through `evalkit.dataset.JsonDatasetStore`, and `report.md` lists failing sessions first | `.venv/bin/python -m pytest apps/api/tests/sim/test_grader.py -q` | exit 0 |
| SC-13 | The sim package and its tests are ruff-format clean | `.venv/bin/ruff format --check apps/api/sim apps/api/tests/sim` | exit 0 |
| SC-14 | The launcher skill has frontmatter and names `make sim-run` | `.venv/bin/python -c "import pathlib,sys; t=pathlib.Path('.claude/skills/user-sim/SKILL.md').read_text(); sys.exit(0 if t.startswith('---') and 'make sim-run' in t else 1)"` | exit 0 |

## 4. Tasks

### Task 1.1 — `claude_cli` wrapper and the fake `claude` (wave 1)

- **Files:** apps/api/sim/__init__.py, apps/api/sim/claude_cli.py, apps/api/tests/sim/__init__.py, apps/api/tests/sim/fixtures/fake_claude.py, apps/api/tests/sim/test_claude_cli.py, .gitignore
- **Action:** Write the tests first. `fake_claude.py` is an executable Python script. It writes its argv to `$FAKE_CLAUDE_ARGV_FILE`, and it emits stream-json lines (a `system` init, a `rate_limit_event`, and a `result` with `structured_output`) selected by `$FAKE_CLAUDE_MODE` (`ok`, `rate_limited`, `bad_json`, `array_shape`). In `ok` mode the `structured_output` is read from `$FAKE_CLAUDE_OUTPUT_FILE` when set; the file holds either one JSON value or a JSON list consumed one item per call. The utilization reported in the rate-limit event comes from `$FAKE_CLAUDE_FIVE_HOUR`, default `0.4`. Every call appends one line to `$FAKE_CLAUDE_CALLS_FILE` when set, so later tasks can assert the call count. Then implement `run(system_prompt, user_prompt, schema, model=None, timeout=120) -> dict`:
  - build the Global Constraints flags and resolve the binary from `SIM_CLAUDE_BIN` (default `claude`);
  - run it through `asyncio.create_subprocess_exec` in a `mkdtemp` cwd and parse the output line by line;
  - accept both the single-object and the array output shapes;
  - set the module-level `last_quota`;
  - raise `QuotaExhausted` or `DriverError` as design §5.1 specifies;
  - expose `cli_version()`.
  Add `apps/api/sim/runs/` to the root `.gitignore`.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/sim/test_claude_cli.py -q`
- **Done:** The tests assert that the argv holds `--setting-sources` followed by `""` and holds no `--bare`, that `last_quota.five_hour` equals `$FAKE_CLAUDE_FIVE_HOUR`, that `rate_limited` raises `QuotaExhausted`, that `$FAKE_CLAUDE_OUTPUT_FILE` drives the returned value, and that `$FAKE_CLAUDE_CALLS_FILE` gains 1 line per call. All tests pass.
- **Criteria:** SC-1
- **Interfaces:** Consumes the claude CLI stream-json format (research-brief). Produces `sim/claude_cli.py` (`run`, `last_quota`, `QuotaExhausted`, `DriverError`, `cli_version`) and `tests/sim/fixtures/fake_claude.py`.

### Task 1.2 — Local identity provider (wave 1)

- **Files:** apps/api/sim/keys.py, apps/api/tests/sim/test_keys.py
- **Action:** Write the test first. Start `KeyServer` on an ephemeral port and build a `Settings` object with `supabase_jwks_url` pointing at it, `supabase_jwt_issuer="sim"`, and the default audience. `_verify_bearer_token(request, settings)` takes a request, so build a `starlette.requests.Request({"type": "http", "headers": [(b"authorization", b"Bearer <token>")]})`. Assert that it accepts the token from `token_for("abc")` and returns an `AuthUser` with `id == "sim-abc"`. Assert that a token signed by a second keypair raises `AuthError`. Clear `_jwks_clients` around the test. Then implement `KeyServer`:
  - an RSA 2048 keypair from `cryptography` and a `uuid4` `kid`;
  - `/.well-known/jwks.json` served by a stdlib `ThreadingHTTPServer` in a daemon thread;
  - the methods `start()`, `stop()`, `url`, and `token_for(persona_id)`.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/sim/test_keys.py -q`
- **Done:** Two tests pass: one accepts the valid token and one rejects the wrong-key token.
- **Criteria:** SC-2
- **Interfaces:** Consumes app.core.auth._verify_bearer_token and app.core.config.Settings. Produces `sim/keys.py` (`KeyServer`).

### Task 1.3 — SSE stream client (wave 1)

- **Files:** apps/api/sim/sse.py, apps/api/tests/sim/fixtures/stream_all_events.txt, apps/api/tests/sim/test_sse.py
- **Action:** Write the fixture first: a raw SSE body containing, in order, `start`, `subagent`, `tool_call`, `tool_result`, `panel`, `token`, `reset`, `token`, `interrupt` (payload type `plan_approval`), `done`, and `error`, with payloads shaped as in `app/streaming/events.py`. Then implement:
  - `SseEvent(name, data)`;
  - `parse(lines) -> Iterator[SseEvent]`;
  - `stream_turn(client, base_url, token, body) -> AsyncIterator[SseEvent]`, which POSTs to `/agent/stream` with a Bearer header and raises `HttpStatusError(status)` when the status is not 200;
  - `to_ui_events(persona_id, ev) -> list[dict]`, which maps events to the design §5.7 types.

  Test both `parse` and `stream_turn` over an `httpx.MockTransport`, including the 401 and 429 cases.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/sim/test_sse.py -q`
- **Done:** The parsed event names equal the 11-item fixture sequence. `to_ui_events` produces `bot_interrupt` with `kind == "plan_approval"`. Status 401 raises `HttpStatusError` with `.status == 401`.
- **Criteria:** SC-3
- **Interfaces:** Consumes the /agent/stream SSE contract (app/streaming/events.py). Produces `sim/sse.py` (`SseEvent`, `parse`, `stream_turn`, `to_ui_events`, `HttpStatusError`).

### Task 1.4 — Event bus, WebSocket, and static UI server (wave 1)

- **Files:** apps/api/sim/bus.py, apps/api/tests/sim/test_bus.py
- **Action:** Write the test first. Start `Bus(run_dir, static_dir, port=0)`, connect 2 `websockets` clients, publish 3 events, then connect a third client. Assert the following:
  - The first two clients each receive 3 events.
  - The third client receives the 3 events of history.
  - `transcript.jsonl` has 3 lines.
  - A plain HTTP GET of `/` returns `index.html` with status 200.

  Then implement `Bus`:
  - `start()`, `stop()`, `publish(event)` (which stamps `t`), and `port`;
  - `websockets.asyncio.server.serve` with a `process_request` hook that serves files from `static_dir` when a request has no upgrade;
  - an in-memory history list.

  Use a temp `static_dir` in the test, so this task does not depend on Task 1.6.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/sim/test_bus.py -q`
- **Done:** All four assertions pass.
- **Criteria:** SC-4
- **Interfaces:** Consumes the websockets package (already installed). Produces `sim/bus.py` (`Bus`).

### Task 1.5 — Read-only DB check (wave 1)

- **Files:** apps/api/sim/db_check.py, apps/api/tests/sim/test_db_check.py
- **Action:** Write the test first. On a temporary SQLite database, create schema via the repositories' `init_db`. Add 1 booking and 1 trip for `sim-a` before `since` and 1 of each after, plus 1 of each for `other-user`. Assert that `snapshot(session_factory, user_id="sim-a", since=...)` returns exactly the post-`since` booking and trip. Then implement:
  - `snapshot(session_factory, user_id, since) -> {"bookings": [...], "trips": [...]}` through `BookingRepository.list_all` and `TripRepository.list_trips`, filtered by `created_at >= since`. `since` is a timezone-aware UTC `datetime`, and a naive `created_at` is treated as UTC before the comparison;
  - `sim_session_factory(url)`, which refuses any URL whose port is not `5434` unless `allow_any=True`.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/sim/test_db_check.py -q`
- **Done:** The snapshot holds 1 booking and 1 trip, both with ids from after `since`. `sim_session_factory("postgresql+psycopg://x@localhost:5433/travel")` raises `ValueError`.
- **Criteria:** SC-7
- **Interfaces:** Consumes app.repositories.booking.BookingRepository, app.repositories.trip.TripRepository, and app.db session helpers. Produces `sim/db_check.py` (`snapshot`, `sim_session_factory`).

### Task 1.6 — 2D lobby UI (wave 1)

- **Files:** tools/sim-ui/index.html, tools/sim-ui/sim.js, tools/sim-ui/sim.css
- **Action:** Build the static lobby from design §5.9, following the mockup (`specs/user-simulation/mockup.html`, published 2026-09-25), which uses the DESIGN.md tokens: Inter, departure-lime, and the flight-status colours.
  - Layout: a canvas scene with an entrance, a queue lane, and a desk with `seats` chairs and a bot avatar per seat. The scene uses the flat isometric direction chosen from `specs/user-simulation/style-study.html` (option B, 2026-09-25). The simulation runs in floor-plan coordinates, a 640×520 room, and `draw()` projects them with `iso(x, y) = (OX + (x - y)·K, OY + (x + y)·K/2)`. Everything is vector-drawn and uses the DESIGN.md tokens (ink, departure-lime, the flight-status colours, and Inter), with soft shadows and no outlines. The room has checker floor tiles, back and left walls with the desk title on the left wall, lime-soft door mats and stand spots, a desk box along the back wall, and queue posts and belts. Travellers are tokens: a capsule body in the persona colour, a round head with skin and hair colours, and a status ring under the feet (lime when selected, otherwise the flight-status colour). Each bot is a dark robot behind the desk with lime eyes and an antenna. Tool and approval chips sit on the desk top. Bot bubbles sit above the robot, with a `Tin <n> · <subagent>` caption. Traveller bubbles sit below the traveller, with the traveller's name as the caption. People are depth-sorted by `x + y`. Roster and panel avatars are the matching token as inline SVG.
  - Motion and bubbles: tweened walks, speech bubbles, a streaming bot bubble, tool icons, and exit badges.
  - Side panel: `#transcript` with one `<li>` per user or bot line for the selected traveller, plus an `#events` tab with the raw event stream.
  - Roster table `#roster` with one `<tr data-id="<persona_id>">` per traveller. Clicking a row or a sprite on the canvas selects that traveller. The DOM rows give the smoke script a stable click target.
  - Header: `#done-count` showing `done/total`, plus `#quota-5h` and `#quota-7d` bars fed by `quota` events.
  - Connection: `sim.js` connects to `ws://${location.host}/ws`, and on reconnect it clears the scene and rebuilds it from the replayed history.
- **Verify:** `node --check tools/sim-ui/sim.js`
- **Done:** `sim.js` parses. `index.html` references only `sim.js` and `sim.css`, with no external URL, and contains the ids `done-count`, `transcript`, `events`, `roster`, `quota-5h`, `quota-7d`, and `scene`.
- **Criteria:** SC-10
- **Interfaces:** Consumes the UI event contract (Global Constraints). Produces `tools/sim-ui/index.html`, `tools/sim-ui/sim.js`, and `tools/sim-ui/sim.css`.

### Task 1.7 — Sim Compose stack and make targets (wave 1)

- **Files:** apps/api/docker-compose.sim.yml, apps/api/Makefile, Makefile
- **Action:** Write `docker-compose.sim.yml` with top-level `name: travel-sim` and two services:
  - `db-sim`: `pgvector/pgvector:pg17`, with user, password, and database all `travel`, host port `5434`, volume `pgdata-sim`, and a healthcheck.
  - `api-sim`: `build: .` and `env_file: .env`, with this environment: `DATABASE_URL=postgresql+psycopg://travel:travel@db-sim:5432/travel`, `SUPABASE_JWKS_URL=http://host.docker.internal:8766/.well-known/jwks.json`, `SUPABASE_JWT_ISSUER=sim`, `ENVIRONMENT=development`, and `WEB_SEARCH_ENABLED=false`. Map port `8001:8000`. Add `extra_hosts: ["host.docker.internal:host-gateway"]`, no bind mount, and no `--reload`.

  Add these targets to `apps/api/Makefile`:
  - `sim-up`: `up -d --build`, then poll `http://localhost:8001/healthz` for up to 90 s.
  - `sim-down`.
  - `sim-reset`: `down -v`.
  - `sim-run`: `$(VENV)/bin/python -m sim --n $(N) --parallel $(PARALLEL)`, plus optional `--personas` and `--seed`. Defaults are `N=8` and `PARALLEL=3`.

  Add root delegating targets with the same names, in the same style as `eval-*`.
- **Verify:** `docker compose -f apps/api/docker-compose.sim.yml config -q`
- **Done:** The config validates. `make -n -C apps/api sim-run N=2 PARALLEL=2` prints a command containing `-m sim --n 2 --parallel 2`.
- **Criteria:** SC-9
- **Interfaces:** Consumes the existing apps/api/Dockerfile and .env. Produces `apps/api/docker-compose.sim.yml` and the `sim-*` make targets.

### Task 2.1 — Persona generator (wave 2)

- **Files:** apps/api/sim/personas.py, apps/api/sim/prompts/persona_generator.md, apps/api/sim/prompts/traveller.md, apps/api/tests/sim/test_personas.py
- **Action:** Write the test first, using the fake `claude` in `ok` mode with a fixture structured output listing 3 personas. Implement:
  - the pydantic `Persona` model with the fields in design §5.2;
  - `generate(n, seed)`, which calls `claude_cli.run` once with the list schema and writes `personas.json`;
  - `load(path)`;
  - `traveller_system_prompt(persona)`, which renders `traveller.md` with the tau-bench rules from design §5.2.
  The generator prompt asks for mixed origins and languages, and for at least one traveller who leaves out the origin or the dates.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/sim/test_personas.py -q`
- **Done:** `generate(3, seed=1)` returns 3 `Persona` objects and writes `personas.json`. `load` of that file equals the result. The fake's argv holds `--json-schema`.
- **Criteria:** SC-6
- **Interfaces:** Consumes `sim/claude_cli.py`. Produces `sim/personas.py` (`Persona`, `generate`, `load`, `traveller_system_prompt`) and `sim/prompts/*.md`.

### Task 2.2 — Conversation driver (wave 2)

- **Files:** apps/api/sim/driver.py, apps/api/tests/sim/test_driver.py
- **Action:** Write the tests first. Use a fake `claude_cli.run` (a scripted list of `{message, intent_done}`), a recording fake bus, a fake `KeyServer.token_for`, and an `httpx.MockTransport` API that serves canned SSE bodies built from Task 1.3's fixture pieces. Test these cases:
  - (a) the session stops on `intent_done`;
  - (b) the session stops at `max_turns`;
  - (c) on `plan_approval`, the next request body has `resume.approved == persona.will_book` and the same `conversation_id`;
  - (d) with 5 travellers and `parallel=2`, the peak in-flight count is 2;
  - (e) with `last_quota.five_hour = 0.9`, no traveller starts after the ceiling and the batch status is `quota`;
  - (f) a 401 gives batch status `auth_misconfigured`;
  - (g) a 429 gives batch status `tier_misconfigured`;
  - (h) a 500 gives that session `bot_error` while the others finish.

  Then implement `run_batch(personas, parallel, base_url, keys, bus, client, set_tier) -> BatchResult` per design §5.6. `set_tier` is an injected callable, and the CLI wires it to `docker compose exec`. The driver publishes `persona_queue`, `walk_to_desk` (with a seat index), `user_say`, the `bot_*` events, `quota`, and `persona_leave`.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/sim/test_driver.py -q`
- **Done:** All 8 scenario tests (a–h) pass.
- **Criteria:** SC-5
- **Interfaces:** Consumes `sim/claude_cli.py`, `sim/sse.py`, `sim/keys.py`, `sim/bus.py`, and `sim/personas.py`. Produces `sim/driver.py` (`run_batch`, `BatchResult`, `SessionResult`).

### Task 2.3 — Grader and reports (wave 2)

- **Files:** apps/api/sim/grader.py, apps/api/sim/prompts/grader.md, apps/api/tests/sim/test_grader.py
- **Action:** Write the test first with a fixture `SessionResult` and a fake `claude_cli.run` that returns a rubric result with verdict `fail`. Implement:
  - `grade(session, db_rows) -> Grade`, one `claude_cli.run` call per session with the design §5.8 rubric;
  - `write_reports(run_dir, batch, grades)`, which writes `report.json`, `report.md` (failing sessions first, plus total `claude -p` calls, total chatbot `usage`, and `cli_version`), and `golden_candidates.json`.

  `golden_candidates.json` goes in its own directory, `runs/<ts>/candidates/`, because `JsonDatasetStore` loads every `*.json` in a directory and `report.json` is not a list. Each candidate is a `Golden` with these fields:
  - `id`: `sim-<batch ts>-<persona_id>`;
  - `suite`: `"sim"`;
  - `language`: the persona's language;
  - `turns`: the traveller's messages in order;
  - `scenario`: `tool_failure` when the session ended in `bot_error`, otherwise `multi_turn`;
  - `capability`: from the first `bot_tool` name. `search_flights` maps to `flight_search`; `search_hotels` and any other name containing `hotel` to `hotels`; `book_*` to `booking`; any name containing `budget` (e.g. `estimate_trip_budget`) to `budget`. A `bot_error` session maps to `errors`, and anything else to `routing`.

  The test loads `runs/<ts>/candidates/` through `JsonDatasetStore(dir, TAXONOMY)` and asserts that `report.md` lists the `fail` session before a `pass` session.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/sim/test_grader.py -q`
- **Done:** `JsonDatasetStore` loads 1 candidate from `candidates/`, with `scenario == "multi_turn"` and `capability == "flight_search"` for a fixture whose first tool is `search_flights`. In `report.md`, the `fail` row's line index is lower than the `pass` row's.
- **Criteria:** SC-12
- **Interfaces:** Consumes `sim/claude_cli.py`, `sim/db_check.py`, evalkit.dataset.JsonDatasetStore, and eval.adapters.config.TAXONOMY. Produces `sim/grader.py` (`grade`, `Grade`, `write_reports`) and `sim/prompts/grader.md`.

### Task 3.1 — CLI entry point and preflight (wave 3)

- **Files:** apps/api/sim/__main__.py, apps/api/tests/sim/test_main.py
- **Action:** Write the tests first. Each of these preflight failures must exit 2 before any `claude` call; the fake `claude` records a call count of 0:
  - `SIM_CLAUDE_BIN` points at a missing path;
  - the base URL is `http://localhost:8000` and `--i-know` is not passed;
  - `OPENAI_API_KEY` is empty in the env file given by `--env-file`;
  - the base URL does not answer `GET /healthz`. The test uses an unused local port.

  Then implement `python -m sim` with these args: `--n`, `--parallel`, `--personas`, `--seed`, `--base-url` (default `http://localhost:8001`), `--i-know`, and `--env-file`. The `--env-file` default is resolved from the package location (`Path(sim.__file__).parents[1] / ".env"`), so `make sim-run` works from `apps/api/`. The run order is:
  1. preflight;
  2. create the `runs/<ts>` directory;
  3. start `KeyServer` and `Bus`;
  4. print the UI URL;
  5. load or generate the personas;
  6. `run_batch`, with `set_tier` wired to `docker compose -p travel-sim exec -T api-sim python -m scripts.set_tier sim-<id> premium`;
  7. grade each session and write the reports;
  8. publish `batch_end`;
  9. keep the bus up for 30 s so the UI can show the final state, then stop.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/sim/test_main.py -q`
- **Done:** All 4 preflight tests pass. Each asserts exit code 2 and 0 lines in `$FAKE_CLAUDE_CALLS_FILE`.
- **Criteria:** SC-8, SC-11, SC-13
- **Interfaces:** Consumes `sim/claude_cli.py`, `sim/keys.py`, `sim/bus.py`, `sim/personas.py`, `sim/driver.py`, `sim/grader.py`, `sim/db_check.py`. Produces `sim/__main__.py`, the `python -m sim` entry.

### Task 3.2 — UI smoke script against the real bus (wave 3)

- **Files:** tools/sim-ui/smoke.mjs, tools/sim-ui/fixtures/transcript.jsonl, apps/api/sim/replay_fixture.py, .gitignore
- **Action:**
  - `replay_fixture.py` starts `Bus` on an ephemeral port (`port=0`), with `static_dir=tools/sim-ui`, and preloads the history from a transcript file. It prints `PORT=<n>` on its first stdout line. This keeps it clear of a live `sim-run` on 8765. It is a test seam, not a user-facing replay mode.
  - `fixtures/transcript.jsonl` holds 2 travellers, with 1 finished and graded, and 4 or more user/bot lines.
  - `smoke.mjs` runs on Node 24 (memory `playwright-mcp-broken-use-node24-script`). `playwright-core` is not hoisted, so it loads it with `createRequire` from the first directory matching `node_modules/.pnpm/playwright-core@*/node_modules/playwright-core`, and exits 2 with a message when there is no match. It then:
    1. spawns `.venv/bin/python -m sim.replay_fixture` from `apps/api/` and reads `PORT=` from its output;
    2. opens `http://localhost:<port>/`;
    3. clicks `#roster tr[data-id="<first persona id in the fixture>"]`;
    4. asserts that `#done-count` reads `1/2` and that `#transcript li` has 4 or more items;
    5. saves `tools/sim-ui/smoke.png` and kills the child process.
  - Add `tools/sim-ui/smoke.png` to the root `.gitignore`.
- **Verify:** `$HOME/.nvm/versions/node/v24.17.0/bin/node tools/sim-ui/smoke.mjs`
- **Done:** Exit 0, and `smoke.png` exists.
- **Criteria:** SC-10
- **Interfaces:** Consumes `sim/bus.py`, `tools/sim-ui/index.html`, `tools/sim-ui/sim.js`. Produces `tools/sim-ui/smoke.mjs` and `apps/api/sim/replay_fixture.py`.

### Task 3.3 — Launcher skill and README (wave 3)

- **Files:** .claude/skills/user-sim/SKILL.md, apps/api/sim/README.md
- **Action:**
  - The README covers setup (`make sim-up`), a run (`make sim-run N= PARALLEL=`), where outputs land, the quota guard and `SIM_QUOTA_CEILING`, `SIM_CLAUDE_MODEL`, and the terms note dated 2026-09-25: `claude -p` draws from shared plan limits, and `--bare` is never used.
  - The skill checks for `api-sim` health (and runs `make sim-up` when it is down), runs `make sim-run`, prints the UI URL, and summarises the failing rows of `report.md` when the batch ends. It holds no simulation logic.
- **Verify:** `.venv/bin/python -c "import pathlib,sys; t=pathlib.Path('.claude/skills/user-sim/SKILL.md').read_text(); sys.exit(0 if t.startswith('---') and 'make sim-run' in t else 1)"`
- **Done:** The skill has frontmatter and names `make sim-run`. The README contains the strings `SIM_QUOTA_CEILING` and `--bare`.
- **Criteria:** SC-14
- **Interfaces:** Consumes the make targets from Task 1.7. Produces `.claude/skills/user-sim/SKILL.md` and `apps/api/sim/README.md`.

## 5. Risks

- **Auth hard gate.** The risk corroboration hook will flag JWT and JWKS strings in `sim/keys.py`.
  The lane is already `high-risk`, and `app/core/auth.py` is not modified.
- **Workflow-engine gate.** It is warn mode and is triggered by `.claude/skills/user-sim/SKILL.md`.
- **Quota contention.** The live smoke run spends the user's plan quota. Keep it to `N=2`.
- **Live acceptance is phase-level UAT, not an SC row.** It runs from the repo root:
  `make sim-up` then `make sim-run N=2 PARALLEL=2`. You open the printed URL, see 2 travellers
  walk to the desk and converse, and `report.md` has 2 rows. Record it in SUMMARY `### Verify`
  with the run directory.
- **The shared image build.** `api-sim` builds from `apps/api/`, so it picks up whatever is
  checked out in that worktree.

## 6. Status Log

- 2026-09-25 — plan written (proposed). Plan review round 1 raised 9 issues, all fixed (fake-claude output/calls files, Golden fields, candidates directory, env-file path, roster DOM target, playwright-core resolution, ephemeral smoke port, gitignore, Request stub). Plan review round 2: approved; advisory fixes applied (tool-name mapping, SC-8 wording). Mockup published; waiting for the user to review it before execution.
