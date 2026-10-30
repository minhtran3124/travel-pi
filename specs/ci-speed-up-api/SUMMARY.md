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
