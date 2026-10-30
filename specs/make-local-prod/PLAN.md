---
status: in-progress
---

# Make targets: `make local`, `make prod`, de-duplicated Makefiles

## Goal

1. `make local` starts the local dev stack in one command: db + redis + worker + api (Docker, foreground with live logs; the owner does not want detached mode).
2. `make prod` starts the Render-topology simulation (today's "prodsim") in one command, foreground with live logs.
3. Remove the duplication in the root and `apps/api` Makefiles.

## Findings (current state)

- Root `Makefile` forwards ~25 targets to `apps/api` one rule at a time; `.PHONY` is listed in both files.
- Root re-declares `N`/`PARALLEL` and re-passes `ARGS`, `PERSONAS`, `SEED` by hand; command-line variables already reach a sub-make on their own.
- The `nvm use 24` snippet is repeated three times.
- Root `help` only matches single-name rules, so every multi-target rule (all `eval-*`, `sim-*`, `prodsim*`) is missing from `make help`.
- `apps/api`: eval flags (`--out ... --html ...`, provider flags) repeated; `dev-anthropic` copies the uvicorn line; the wait-for-health loop exists only in `sim-up`.
- `docker-compose.prodsim.yml`: `api-1`/`api-2` repeat the `depends_on` that `*web` already carries.
- `make up` is foreground; the API seeds itself on startup, so a separate seed step is not needed for the Docker stack.

## Design

- Root: one `API_TARGETS` list + one pattern rule forwarding to `apps/api`. Root keeps only FE/turbo targets and `help`.
- `apps/api`: shared `wait_http`, `PY`, eval flag variables; per-group `.PHONY`.
- New names: `local`, `local-down`, `local-logs`, `local-reset`; `prod`, `prod-down`, `prod-logs`, `prod-verify`, `prod-chaos`, `web-prod`.
- Old names stay as one-line aliases: `up`, `down`, `logs`, `prodsim`, `prodsim-up`, `prodsim-chaos`, `prodsim-down`, `web-prodsim`.
- No behaviour change for the old names: `make up` and `make prodsim-up` were already foreground, and the new targets keep that. The only thing dropped is the wait-for-health step, which cannot run after a foreground `up`.

## Steps

1. Rewrite `apps/api/Makefile` (helpers, `local`, `prod`, aliases, dedupe). Done when: `make -C apps/api help` lists every target; `make -n` on each group parses.
2. Rewrite root `Makefile` (pattern forwarding, FE helper, help). Done when: `make help` lists every target; `make -n sim-run N=2 SEED=1` forwards the variables.
3. Trim `docker-compose.prodsim.yml` and update its header. Done when: `docker compose -f docker-compose.prodsim.yml config -q` passes.
4. Update docs (`CLAUDE.md`, `README.md`, `apps/api/README.md`). Done when: grep finds no stale `make up` meaning.
5. Verify end to end. Done when: `make local` -> api healthy; `make prod` -> lb healthy on :8080; `make prod-verify` exits 0; `make test` still passes.
