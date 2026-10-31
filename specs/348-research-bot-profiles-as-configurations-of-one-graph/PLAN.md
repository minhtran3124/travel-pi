# Plan: research bot profiles (Tin, Min ...) as configurations of one graph, for A/B eval (#348)

## Goal
Design bot profiles as persona configurations of the single LangGraph graph so variants run on the same eval set. Research only: this file is the whole deliverable, no code.

## Lane
**high-risk.** Reasons: (1) an Alembic migration (new `bots` table, new `bot_id` columns on `conversations` and `agent_runs`); (2) the `AgentConfigCache` key changes from `agent_name` to `(bot_id, agent_name)`, which touches every LLM resolution path. The follow-up implementation tickets take this lane; this research ticket itself changes no code.

## Status of dependencies
- #345 (instance_id): **merged**. `apps/api/app/core/instance.py` (`resolve_identity`, `BotIdentity`), `services/bots_service.py`, `db/models/bot_heartbeat.py` and `agent_runs.instance_id` exist. Note: "bot" there means a container instance; this plan's "bot" is a persona. See Naming.
- #347 (eval fix): **open dependency, NOT done, out of scope here.** Per-bot A/B comparison is only trustworthy after #347 lands. Tasks T1 to T5 do not need it; the real comparison run after T6 is blocked on it.
- The paid eval (`make eval-check`) is NOT run by this ticket or by any verify command below; only `--dry-run`, unit tests and keyless smoke are used.

## Current surfaces (found by grep)
- Config cache: `app/core/agent_config_cache.py` (`AgentConfigCache._cache: dict[str, AgentModelOverride]`, `get(agent_name)`, `sync_from_cache`, `generation()`); writer `app/services/agent_config_service.py` (`AgentConfigCache.invalidate()`); readers `app/clients/llm.py` (`get_agent_llm`), `app/routers/agent.py` (reflection), `app/agents/graph.py` (cache generation drives graph rebuild).
- Prompts: file-backed registry `app/prompts/registry.py` (`registry.get(name, version=None)`), active versions in `app/prompts/active.yaml`, files `app/prompts/<name>/vN.md`. Supervisor reads `registry.get("supervisor")` in `agents/supervisor.py`. Attribution map in `agents/prompt_map.py`.
- Thread id: `_thread_id(user_id, trip_id, conversation_id)` in `app/routers/agent.py` gives `user_<uid>_trip_<tid>_conv_<cid>`.
- agent_runs: `app/db/models/agent_run.py` (has `thread_id`, `conversation_id`, `instance_id`).
- Eval: `apps/api/eval/__main__.py` (travel-pi wiring over `evalkit`; it already strips a travel-pi-only `--provider` flag before evalkit parses argv), datasets `eval/datasets/*.json` (84 cases), baselines `eval/baselines/main.json`, Make targets `eval-smoke`, `eval-full`, `eval-compare`, `eval-check` in `apps/api/Makefile`.

## Answers to the 7 spike questions

1. **Where does the profile live?** A small `bots` table: `id`, `slug` (unique, e.g. `tin`, `min`), `name`, `prompt_versions` (JSON: prompt name to version), `model_overrides` (JSON: agent_name to provider/model/temperature), `enabled_specialists` (JSON list, subset of `ALL_SUBAGENTS`), `enabled` (bool), timestamps. A `default` row mirrors today's behaviour so existing data is unchanged. Prompt TEXT stays in versioned files; the table only selects versions. Rejected: one deployment per bot (contradicts the one-graph goal, multiplies ops cost); YAML-only profiles (no runtime toggle like `agent_config` already has; acceptable fallback if the migration is vetoed).
2. **How does a request pick a bot?** `conversations.bot_id` (FK to `bots.id`, NOT NULL, default = default bot), fixed at conversation creation and never changed. Creation reads a server-side setting (`DEFAULT_BOT_SLUG`) or, for eval only, an explicit slug from the harness. Rejected: per-request bot choice (breaks thread consistency and checkpointer state).
3. **Config key.** `AgentConfigCache` key becomes `(bot_id, agent_name)`. Resolution order: bot override, then global `agent_config` row for `agent_name` (today's behaviour), then env default. `get_agent_llm(agent_name, bot_id=None)`; `None` resolves to the default bot so every current caller keeps working. `generation()` stays process-wide. The `agent_config` table is unchanged; per-bot overrides live in `bots.model_overrides`.
4. **thread_id and agent_runs.** Add `bot_id` to `agent_runs` (nullable, indexed, backfilled to the default bot) next to `instance_id`. For `thread_id`, do NOT change the format for existing conversations (would orphan checkpoints). New format `user_<uid>_trip_<tid>_bot_<slug>_conv_<cid>` applies only to non-default-bot conversations created after the migration; `_thread_id` takes the conversation's stored bot and omits the segment for the default bot. `conversation_id` is already unique, so the bot segment is for log readability and eval isolation.
5. **Prompts per bot.** Versioned files stay the source of truth. `registry.get(name, version=None, bot=None)`: version is `bot.prompt_versions[name]` if present, else `active.yaml`. A bot needing different text adds new `vN.md` files (follow `app/prompts/CHANGELOG.md`); no per-bot copies of unchanged prompts. `prompt_map.py` attribution must record the resolved version per bot. One compiled graph serves all bots; enabled specialists are applied as a routing filter in the supervisor, not by compiling separate graphs.
6. **Eval per bot and comparison.** Add `--bot <slug>` to `eval/__main__.py` (stripped before evalkit parses argv, like `--provider`); the runner creates each case's conversation with that bot. Run all 84 cases once per bot, write `eval/reports/<bot>.json`, compare with the existing `eval-compare` path (baseline = default bot's report). New target `make eval-bots BOTS="default tin min"` loops. Report JSON records the `bot` slug. The paid judged run (`eval-check`) is a later manual step gated on #347.
7. **User-facing picker?** **No. Default is no user-facing bot picker**; variants exist for evals and the server-side default only. This follows `PRODUCT.md` ("make the next decision and move on"): a persona chooser adds a decision the user should not make. A picker can be proposed in a separate ticket if A/B results justify it.

## Naming
#345 uses "bot" for a container instance (`BotIdentity`, `bots_service`, `bot_heartbeat`). To avoid collision, implement the new table as `bot_profiles` with `bot_profile_id`, keeping the ticket wording `bots`/`bot_id` in prose, unless #344 has already renamed the instance concept.

## Implementation tasks (for follow-up tickets, in order)

### T1. Migration and models
- Files: `apps/api/alembic/versions/<new>_add_bot_profiles.py`, `apps/api/app/db/models/bot_profile.py`, `apps/api/app/db/models/conversation.py`, `apps/api/app/db/models/agent_run.py`
- Covers: AC1
- Effort: high (migration plus backfill to default bot)
- Verify: `cd apps/api && ../../.venv/bin/alembic upgrade head && ../../.venv/bin/alembic downgrade -1 && ../../.venv/bin/alembic upgrade head` exits 0; `../../.venv/bin/python -m pytest tests -k bot_profile -xvs` exits 0.

### T2. Repository, service, default-bot seed
- Files: `apps/api/app/repositories/bot_profile.py`, `apps/api/app/services/bot_profile_service.py`, `apps/api/scripts/seed*.py`, `apps/api/tests/services/test_bot_profile_service.py`
- Verify: `cd apps/api && ../../.venv/bin/python -m pytest tests/services/test_bot_profile_service.py -xvs` exits 0.

### T3. Config key (bot_id, agent_name)
- Files: `apps/api/app/core/agent_config_cache.py`, `apps/api/app/clients/llm.py`, `apps/api/app/services/agent_config_service.py`, `apps/api/app/routers/agent.py`, `apps/api/app/agents/graph.py`, `apps/api/tests/core/test_agent_config_cache.py`
- Effort: high (touches every LLM resolution path; `bot_id=None` must stay behaviour-identical)
- Verify: `cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_agent_config_cache.py tests/clients -xvs` exits 0, and `make test` stays green.

### T4. Per-bot prompts and specialist filter
- Files: `apps/api/app/prompts/registry.py`, `apps/api/app/agents/supervisor.py`, `apps/api/app/agents/prompt_map.py`, `apps/api/tests/prompts/test_registry_bot.py`
- Verify: `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts -xvs` exits 0.

### T5. bot_id in conversation creation, thread_id and agent_runs
- Files: `apps/api/app/routers/agent.py`, `apps/api/app/repositories/agent_run.py`, `apps/api/app/services/conversation_service.py`, `apps/api/tests/api/test_agent_bot_id.py`
- Verify: `cd apps/api && ../../.venv/bin/python -m pytest tests/api/test_agent_bot_id.py -xvs` exits 0; a test proves the old thread_id format still resolves.

### T6. Eval `--bot` flag and comparison (real comparison blocked on #347)
- Files: `apps/api/eval/__main__.py`, `apps/api/Makefile`, `apps/api/eval/README.md`, `apps/api/tests/eval/test_bot_flag.py`
- Verify (keyless, free): `cd apps/api && ../../.venv/bin/python -m eval --suite smoke --dry-run --bot tin` exits 0 and lists the goldens; `../../.venv/bin/python -m pytest tests/eval/test_bot_flag.py -xvs` exits 0. Do NOT run `make eval-check`.

### T7. Docs
- Files: `WORKFLOW.md`, `FEATURES.md`, `apps/api/app/prompts/CHANGELOG.md`
- Verify: `grep -n "bot profile" WORKFLOW.md FEATURES.md` returns at least 1 line each.

## Risks
- Config-key change silently dropping overrides: mitigated by the `bot_id=None` default-path test in T3.
- Naming collision with the #345 instance meaning of "bot": see Naming.
- A/B numbers are meaningless until #347 is fixed.

## Verify for THIS ticket
- `git diff --stat` shows only this PLAN.md added.
- `grep -c "#347" PLAN.md`, `grep -c "high-risk" PLAN.md` and `grep -c "picker" PLAN.md` each return at least 1.
