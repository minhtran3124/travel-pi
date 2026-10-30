# ci-speed-up-api — SUMMARY

**Problem:** the `api` CI job took 16–18 min per PR (run 41077561329: 4089 passed in 952 s).
Install was ~2 s (setup-uv already caches), so the whole cost was the single-process pytest run.

**Changes**
- `pytest-xdist` + `-n auto` in CI and `make test` (4 vCPU on the public-repo runner).
- `--durations=30` in CI to expose the slowest tests for the next round.
- `changes` job: the `api` job runs only when the PR touches `apps/api/**` or `ci.yml`.
  Uses `if` (skipped = passing for required checks), not `on.paths`.
- `concurrency` cancels the superseded run on a new push; `api` gets a 30 min timeout.

**Not done (pending data):** `seeded_session` (tests/conftest.py) re-runs `seed_all` per test
(150 uses / 22 files). Decide after reading `--durations` from the first CI run.

**Verify:** compare `api` job time to the 952 s baseline; test count must stay 4089 passed, 17 skipped.

## Round 2 — test setup cost (branch ci/api-test-setup-speedup)

`--durations` from PR #368 showed many 3–7 s tests in booking/trip/place ownership files.
Measured cause: each `with TestClient(create_app())` runs the full lifespan (~1 s: re-seed,
RAG ingest, agent graph, research agent), and those helpers enter it several times per test
and also call `seed_all` (~0.7 s, idempotent) every time.

- `tests/fixtures/light_app.py`: `ensure_seeded(url)` (seed once per DB per process) and
  `create_app_without_lifespan()`.
- Applied to the 6 `_client_as` helpers + `test_premium_gate`: 71 tests, ~150 s → 31 s serial.
- `seeded_session` (tests/conftest.py) uses `ensure_seeded`: 20 files, 391 passed, 6 skipped.

Left alone: files that need the real lifespan (`agent_chat`, `feedback`, `sim/test_driver`);
the first `client` use per xdist worker (~3.5 s, one-off); `tests/rag/conftest.py` (own DB per test).
