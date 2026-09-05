# catalog-content-i18n — Summary

Lane: high-risk
Confidence: medium
Reason: hard gate `data-loss/migration` (new translations table via Alembic); plus flags existing-behavior (panel localization path), multi-domain (tools + services + streaming + FE parity).
Flags: data model, existing behavior, multi-domain
Affects: app/streaming/panel_localizer.py, app/streaming/panels/*, app/services/place_service.py (+ hotel), app/tools/place_tools.py, app/db/models (new table), app/agents/supervisor.py + state.py (language constant)
Input-type: new spec
Route: brainstorming (design.md, this intake) → approval → xia2 → writing-plans → using-git-worktrees → subagent-driven-development
Escalate: no (hard gate narrowed by the user on 2026-09-05: additive table only; design forks decided — see design.md § Decisions)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> làm hướng 1 đi, mở spec riêng.
> - suy nghĩ về việc place/hotel/etc nên có multiple version languages
> - define constant cho list language, đảm bảo thống nhất về language dùng trong cả app
> - update query kèm theo language để việc get đúng data và nhanh nhất có thể

Context: "hướng 1" = cache translated panel prose per entity id so the `vi` side panel stops
paying one translator LLM call per place description on every search (see
`specs/sse-tool-event-thread-replay/SUMMARY.md`, which fixed the ×N replay but left 4 calls
per search).

## What changed

Branch `feat/catalog-content-i18n` (stacked on `fix/sse-tool-event-thread-replay`, PR #140):

- `app/core/languages.py` is the single owner of language codes (`SUPPORTED_LANGUAGES`,
  `DEFAULT_LANGUAGE`, `normalize`, `LANGUAGE_NAMES`); supervisor / state / SSE events /
  mapper / panel_localizer import it, an architecture test forbids new literals, and a parity
  test pins the list to the FE `locales` array.
- New table `content_translations` (Alembic `a7c3e9f1b2d4`, additive) + `ContentTranslationRepo`
  (`get_many` on the unique key, `upsert_many`).
- `ContentTranslationService.localize(entity_type, items, fields, language)`: overlays stored
  text, translates only the misses in ONE structured LLM call (reusing the `extract_memory`
  agent config), writes them back, keeps source text on any failure; default language is a
  strict no-op.
- `search_places` receives `language` via `InjectedState` and localizes the panel's
  descriptions before building it (model and traveller see the same text). No `language`
  (MCP / direct) → unchanged English output.
- SSE path is LLM-free: `panel_localizer` / panels keep only bounded `vi` swaps; the mapper
  translator closure and `graph.translate_llm` are gone.
- `seed_all` upserts `app/data/content_translations.<lang>.json` (`source="seed"`);
  `scripts/generate_translations.py --language vi` fills that file from the seeded catalog
  — run in the dev container on 2026-09-05: 506/506 place descriptions translated by `gpt-5.4-mini` (extract_memory config), 0 translator failures; the file is checked in.

### Rationale

The three bullets are one feature: a durable, language-keyed store of catalog text
(translation cache = multi-language versions = language-aware query). An in-process dict
would satisfy "hướng 1" alone but is per-worker, lost on restart, and would be thrown away
by the DB-backed version the other two bullets require — so the design goes straight to
the durable store and treats the LLM translator as its miss-path filler.

### Alternatives considered

- documented in `design.md` (§ Options A/B/C for storage; § Options 1/2 for where localization runs)

### Deviations

- **Task 3.2 (hotel tools) not implemented — needs a user decision.** Neither
  `HotelsPanelHotel` nor the FE `HotelsPanel.tsx` carries a `description`, so localizing it at
  tool time would spend LLM calls on text nobody sees (rules/behavior.md §2, no speculative
  code). The store/service/seed already accept `entity_type="hotel"`; wiring is a ~20-line
  follow-up once the hotel panel shows a description (BE field + FE card).
- Rule 1: migration `down_revision` pointed at `f3b7c9d1e5a2` while main's head was `b2d9f4a7c1e8` (two heads); fixed to `b2d9f4a7c1e8` before merge. The offline round-trip test could not see it (it upgrades from the declared parent only) — `alembic heads` is now part of the deploy note.
- Rule 2: `generate_translations.py` calls `reload_from_db` first; outside the app lifespan `AgentConfigCache` is empty and `get_agent_llm` would fall back to the env model.
- Rule 3: `apps/api/scripts/` is gitignored; `generate_translations.py` added with `git add -f`
  like the sibling scripts.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| languages constants + FE parity | `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc1.db ../../.venv/bin/python -m pytest tests/core/test_languages.py -q` | 0 | 4 passed | SC-1 |
| table / migration round-trip / repo | `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc2.db ../../.venv/bin/python -m pytest tests/db/test_content_translations_migration.py tests/repositories/test_content_translation_repo.py -q` | 0 | 5 passed (+ test_db_models table registry) | SC-2 |
| localize service (batch, write-back, no-op, failure) | `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc3.db ../../.venv/bin/python -m pytest tests/services/test_content_translation_service.py -q` | 0 | 8 passed | SC-3 |
| search_places tool-time localization | `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc4.db ../../.venv/bin/python -m pytest tests/tools/test_place_tools_language.py -q` | 0 | 4 passed (23 with existing place tool tests) | SC-4 |
| hotel tools unchanged (Task 3.2 deferred) | `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc5.db ../../.venv/bin/python -m pytest tests/tools/test_hotel_tools.py -q` | 0 | existing suite, no hotel file touched | SC-5 |
| SSE path LLM-free, streaming suites | `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc6.db ../../.venv/bin/python -m pytest tests/streaming/test_panel_localizer.py tests/streaming/test_mapper_language.py tests/streaming/test_panel_language_e2e.py tests/streaming/test_places_panel.py tests/streaming/test_hotels_panel.py tests/agents/test_graph_translate_handle.py -q` | 0 | part of 63 passed (tests/streaming + stream events) | SC-6 |
| seed pre-fill + generator | `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc7.db ../../.venv/bin/python -m pytest tests/db/test_seed_translations.py -q` | 0 | 3 passed (8 with test_seed) | SC-7 |
| no language literals | `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc8.db ../../.venv/bin/python -m pytest tests/architecture/test_language_literals.py -q` | 0 | 1 passed | SC-8 |
| generate vi translations (dev container) | `docker exec api-api-1 python -m scripts.generate_translations --language vi` | 0 | wrote 506 rows; DB check: places 506 / rows 506 / untranslated 0 | SC-7 |
| full BE suite | `make test` | 2 | 2120 passed, 5 failed — identical pre-existing set on `main` (local `.env` provider keys: langfuse/openai/openrouteservice) | |

### Not auto-verified

- Postgres: `alembic upgrade head` on a DB whose lifespan `create_all` already created the table fails with DuplicateTable — `alembic stamp head` there (done on the dev container). A fresh prod DB migrating before first boot upgrades cleanly (revision chain re-verified after fixing `down_revision` → `b2d9f4a7c1e8`; SQLite round-trip re-run).
- Vietnamese text quality of the 506 generated rows — reached provenance (every row differs from its English source, none kept the source on failure); not reviewed by a human. The file is data: hand-edit and re-seed.

### Rollback

- `cd apps/api && ../../.venv/bin/alembic downgrade b2d9f4a7c1e8` (drops `content_translations` only; no existing column touched), then `git revert` the branch commits (e5f3543, bffc378, and the wave-4 commit).

### Harness-Delta

- none
