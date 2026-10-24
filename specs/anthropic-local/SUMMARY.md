# Summary: run the whole stack on Anthropic locally

Issues #268 (switching), #269 (local config), #270 (real local test); milestone "Anthropic local rollout". Stacked on `feat/anthropic-provider` (PR #267). Sub-PRs #271-#274 merged into `feat/anthropic-local`; final PR #275.

## What shipped

| Issue | PR | Result |
|---|---|---|
| #268 | #271 | Per-agent provider override no longer inherits the global `LLM_BASE_URL`; a stored model from another vendor (`gpt-*` on Anthropic, `claude-*` on OpenAI) warns and uses the provider's tier default; `seed_agent_config --provider anthropic` derives the model per provider and tier; offline matrix test (all-openai, all-anthropic, mixed); README "Switching LLM providers". |
| #269 | direct commit | `make api-anthropic`, `make dev-anthropic`, `make seed-anthropic`; `scripts.seed_agent_config --preset anthropic-local` (idempotent, 13 rows). `.env` is not edited: the switch is process env plus `agent_config` rows. |
| #270 | #272, #273, #274 | Bugs found by the real local test, fixed with failing tests first (below). |

## How to run locally on Anthropic

Set in `apps/api/.env`: `LLM_PROVIDER=anthropic`, `LLM_MODEL=claude-sonnet-5-5`, `FAST_LLM_MODEL=claude-haiku-5-5`, then `make up && make seed-anthropic && make api-anthropic`. `agent_config` rows in the DB beat env vars, so seed them (restart the API afterwards: the config is cached).

## Model mapping

| Model | Agents |
|---|---|
| `claude-haiku-5-5` | summarize, reflection, extract_memory, date_resolution, trip_research_grader |
| `claude-sonnet-5-5` | supervisor, planner, concierge, journal, booking, budget, synthesize, trip_research |
| `claude-opus-5-5` | none (about 5x Sonnet cost; set it on the `trip_research` row only if Sonnet proves inadequate) |

Journal and budget are in `FAST_AGENTS` (default Haiku) but are pinned to Sonnet by the seeded rows. Supervisor is in `FAST_MODEL_AGENTS` (cold-cache default Haiku) but is pinned to Sonnet by the seeded row. Live runs confirmed in `agent_runs.by_model` that only Haiku and Sonnet served requests.

## Real local test (Anthropic + local Postgres)

Nine areas: routing, planner, concierge, journal-budget, booking, streaming, research, memory-cost, REST/web. Every area ended `partial`. Approx. spend 7.4 USD (the testers' own estimates). Full per-area evidence is in the private report artifact: https://claude.ai/artifact/Ktv85zQDDRwBJTMijqn4kQ

Fixed and retested live:
- Embeddings hardcoded to OpenAI broke memory tools under Anthropic (429): `EMBEDDING_PROVIDER` setting and a `ResilientEmbeddings` wrapper that falls back to non-semantic vectors for 300s (#273).
- One failing tool degraded a whole parallel batch and the assistant said a committed `create_trip` had failed; `list_trips` was blocked by `trip_guard` with no trip open (#272).
- Provider auth/availability failures returned HTTP 200 or leaked raw provider text: now 502 on `/agent/chat` and SSE `llm_auth` / `llm_unavailable` with sanitized messages; conversation ownership enforced (404); non-UUID `conversation_id` and NUL bytes return 422; resume validates `conversation_id`, existence and a pending interrupt (#274).
- Research live SSE emitted no progress events; Haiku calls were missing from `agent_run_steps`; background memory-extraction cost was missing from `cost_usd` (retest: 31 `research_phase`, 182 `research_tool`, 1 `research_done`; step counts match `by_model`).

Not reproduced live (covered by unit tests only): duplicate parallel `add_itinerary_item` rows, the unrequested "Traveller preferences" note, tool-failure isolation, the 409 on resume without a pending interrupt.

## Verification (this branch)

- `ruff check app scripts`: All checks passed.
- Full `pytest` (apps/api): 3933 passed, 8 skipped, 6 failed in the Finish run.
- Rerun of the 6 failures (follow-up): 5 of them fail only when the worktree's symlinked real `apps/api/.env` is in the cwd (`test_config_llm.py::test_llm_defaults_require_no_key`, `::test_langfuse_disabled_by_default`, `test_config_web_search.py::test_web_search_settings_have_off_defaults`, `test_embeddings.py::test_get_embeddings_fake_without_key`, `::test_warns_for_anthropic_without_openai_key`). Run from a cwd without `.env`, all 32 tests in those four files pass. The sixth, `tests/sim/test_bus.py`, passed 7 of 7 reruns (4 passed each time), so the flake did not reproduce.
- Not re-run: web lint/tests (web unchanged), CI (GitHub billing/spending-limit error blocked every job earlier).

## Known gaps and follow-ups

- Default-settings tests used to read the real `.env` and fail on a machine with real keys (5 tests). Fixed: `tests/core/conftest.py::isolated_settings_env` runs them in a temp cwd with the `Settings` env vars cleared; `tests/core` passes with and without a `.env`. Other test directories were not checked against a real `.env`.
- Research finishes with `review=needs_review`; not investigated (grader strictness vs thin data).
- No per-step `agent_run_steps` row for `extract_memory` (its cost is now merged into the run).
- Some `tool_call` SSE events in the first parallel batch have no matching `tool_result`.
- No chat tool to edit or delete a trip; reply wording leak and weather routing not re-checked.
- Authenticated REST/web UI and the real Supabase JWT path were not exercised (tests used auth overrides on private instances); `make dev-token` not run.
- OpenAI half is tested offline only (credit exhausted, 429); mixed-provider live behaviour (#257) is still unverified. Embeddings and the eval judge stay on OpenAI: Anthropic has no embeddings API.
- Claude prices come from the issue text, not the pricing page.
- Test users and threads from the live runs remain in the local DB.
- An `OPENAI_API_KEY` value was printed in one agent's tool output by a pytest assertion message; rotate that key.
