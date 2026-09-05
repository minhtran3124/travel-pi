---
slug: catalog-content-i18n
status: shipped
owner: Minh Tran
created: 2026-09-05
---

# catalog-content-i18n — Language-keyed catalog text (durable translation store)

**Base:** `main`. **Branch:** `feat/catalog-content-i18n`.
Decisions in `design.md` (§ Decisions, user-approved 2026-09-05); local map in `research-brief.md`.

## Global Constraints

- Every `Verify` / SC check is one pipe-free command under 60s run from `apps/api` with the env
  guard `OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/<x>.db ../../.venv/bin/python -m pytest … -q`
  (empty key, not `env -u`: dotenv would win). Never the whole suite in a row.
- Additive schema only: one new table `content_translations`, one Alembic revision with
  `down_revision = "b2d9f4a7c1e8"`, `downgrade` drops the table. No existing column touched.
- Language codes come only from `app/core/languages.py`; no new `"en"` / `"vi"` literal outside
  that module, its tests, and the `vi` lookup tables already in `app/streaming/panels/*.py`.
- The translator LLM is resolved with `get_agent_llm("extract_memory")` (existing config name);
  do NOT introduce a new agent-config name (null-model seed trap, see research-brief).
- Translation is best-effort: a translator failure logs and keeps the source text; nothing on the
  tool path may raise because of localization. No LLM call when `language == DEFAULT_LANGUAGE`.
- Free-form text is translated at most once per `(entity_type, entity_id, field, language)`:
  the tool path never calls the LLM for a row that already exists.
- MCP callers (no injected `language`) keep today's English behavior.
- Same-wave tasks share no files. Stage and commit as separate commands; no Claude attribution
  trailers.

## 1. Motivation

`vi` side panels pay one LLM translation per place description on every search for text that
never changes; language codes are scattered literals; catalog entities have a single language.
`design.md` §Problem. Prior fix `specs/sse-tool-event-thread-replay` removed the ×N replay but
left 4 calls per search.

## 2. Non-goals

Translating the agent's own prose (`with_reply_language` already does); user-generated content;
a translations admin UI; other panel kinds (weather/route/flights have no free text); new
languages beyond `en`/`vi` (the table supports them, nothing else is wired).

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | `SUPPORTED_LANGUAGES` / `DEFAULT_LANGUAGE` / `normalize()` exist, unknown codes normalize to `en`, and the BE list equals the FE `locales` array | `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc1.db ../../.venv/bin/python -m pytest tests/core/test_languages.py -q` | exit 0 |
| SC-2 | The `content_translations` table is registered with a unique key on (entity_type, entity_id, field, language); the revision upgrades from empty and downgrades cleanly on SQLite; the repo can get_many / upsert_many | `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc2.db ../../.venv/bin/python -m pytest tests/db/test_content_translations_migration.py tests/repositories/test_content_translation_repo.py -q` | exit 0 |
| SC-3 | `localize()` overlays stored text, translates only the missing rows in ONE batched LLM call, writes them back, is a no-op for the default language, and keeps source text when the translator fails | `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc3.db ../../.venv/bin/python -m pytest tests/services/test_content_translation_service.py -q` | exit 0 |
| SC-4 | `search_places` with injected `language="vi"` returns a panel whose descriptions are Vietnamese, a second identical call makes zero LLM calls, and a call without `language` is byte-identical to today | `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc4.db ../../.venv/bin/python -m pytest tests/tools/test_place_tools_language.py -q` | exit 0 |
| SC-5 | Hotel tools are deliberately unchanged (neither `HotelsPanelHotel` nor the FE hotel card carries a description, so tool-time localization would be unseen LLM cost); `search_hotels` / `browse_hotels` behave exactly as before | `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc5.db ../../.venv/bin/python -m pytest tests/tools/test_hotel_tools.py -q` | exit 0 |
| SC-6 | The SSE path no longer calls an LLM for panels: `panel_localizer` keeps bounded swaps only, `mapper` has no translator, the compiled graph exposes no `translate_llm`; existing language/e2e stream tests pass | `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc6.db ../../.venv/bin/python -m pytest tests/streaming/test_panel_localizer.py tests/streaming/test_mapper_language.py tests/streaming/test_panel_language_e2e.py tests/streaming/test_places_panel.py tests/streaming/test_hotels_panel.py tests/agents/test_graph_translate_handle.py -q` | exit 0 |
| SC-7 | `seed_all` loads `app/data/content_translations.vi.json` when present (idempotent), and the generator script writes that file's shape from a fake translator | `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc7.db ../../.venv/bin/python -m pytest tests/db/test_seed_translations.py -q` | exit 0 |
| SC-8 | No `"vi"` / `"en"` literal remains in supervisor / state / events / mapper / panel_localizer | `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/sc8.db ../../.venv/bin/python -m pytest tests/architecture/test_language_literals.py -q` | exit 0 |

## 4. Tasks

### Task 1.1 — Language constants module + replace literals (wave 1)

- **Files:** apps/api/app/core/languages.py, apps/api/app/agents/supervisor.py, apps/api/app/agents/state.py, apps/api/app/streaming/events.py, apps/api/app/streaming/mapper.py, apps/api/app/streaming/panel_localizer.py, apps/api/tests/core/test_languages.py, apps/api/tests/architecture/test_language_literals.py
- **Action:** Create `app/core/languages.py` with `SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "vi")`,
  `DEFAULT_LANGUAGE = "en"`, `Language = Literal["en", "vi"]`, `LANGUAGE_NAMES = {"en": "English", "vi": "Vietnamese"}`
  and `normalize(code: str | None) -> str` (lower/strip; unknown or empty → `DEFAULT_LANGUAGE`).
  Replace the literals: supervisor default + prompt text (list the codes from the constant),
  `state.py` type comment, `events.py` defaults, `mapper.py` seed, `panel_localizer.py`
  `if language != "vi"` → `if normalize(language) == DEFAULT_LANGUAGE` (and dispatch stays
  `localize_vi` for now — renamed in 3.3). Tests: `test_languages.py` covers normalize + a parity
  test that parses `apps/web/src/i18n/config.ts` (`locales = [...]`) and asserts equality;
  `tests/architecture/test_language_literals.py` greps the five modules for `"vi"`/`'vi'`/`"en"`/`'en'`
  and asserts none.
- **Verify:** `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/t11.db ../../.venv/bin/python -m pytest tests/core/test_languages.py tests/architecture/test_language_literals.py tests/agents/test_supervisor_language.py tests/streaming/test_events_language.py -q`
- **Done:** constants module exists, five modules literal-free, FE parity test green, existing language tests green
- **Criteria:** SC-1, SC-8
- **Interfaces:** Consumes: the FE locales array in apps/web/src/i18n/config.ts (existing file). Produces: `apps/api/app/core/languages.py` (SUPPORTED_LANGUAGES, DEFAULT_LANGUAGE, normalize, LANGUAGE_NAMES).

### Task 1.2 — `content_translations` model, migration, repository (wave 1)

- **Files:** apps/api/app/db/models/content_translation.py, apps/api/app/db/models/__init__.py, apps/api/alembic/versions/a7c3e9f1b2d4_add_content_translations.py, apps/api/app/repositories/content_translation.py, apps/api/tests/db/test_content_translations_migration.py, apps/api/tests/repositories/test_content_translation_repo.py
- **Action:** ORM `ContentTranslation(UUIDBase)`: `entity_type: str`, `entity_id: str`, `field: str`,
  `language: str`, `text: Text`, `source: str` (`"seed" | "llm"`), `updated_at: str`, with
  `UniqueConstraint("entity_type","entity_id","field","language", name="uq_content_translations_key")`
  and an index on `(entity_type, language)`. Export from `models/__init__.py`. Alembic revision
  `a7c3e9f1b2d4` (`down_revision="b2d9f4a7c1e8"`), additive, mirrors `e3b7c5d9a1f4` style; downgrade
  drops the table. Repo `ContentTranslationRepo(Repo)`: `get_many(entity_type, entity_ids, fields, language) -> dict[tuple[str,str], str]`
  keyed `(entity_id, field)` (single `IN` query) and `upsert_many(rows: list[dict])` (merge by the unique
  key; flush in live-session mode, commit in factory mode per `Repo`). Migration test follows
  `tests/db/test_agent_runs_migration.py`.
- **Verify:** `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/t12.db ../../.venv/bin/python -m pytest tests/test_db_models.py tests/db/test_content_translations_migration.py tests/repositories/test_content_translation_repo.py -q`
- **Done:** model registered, upgrade/downgrade clean on SQLite, repo get_many/upsert_many tested incl. upsert-overwrite
- **Criteria:** SC-2
- **Interfaces:** Consumes: the existing Repo base class and UUIDBase. Produces: `apps/api/app/db/models/content_translation.py`, `apps/api/app/repositories/content_translation.py` (get_many, upsert_many), `apps/api/alembic/versions/a7c3e9f1b2d4_add_content_translations.py`.

### Task 2.1 — `ContentTranslationService.localize` with batched miss-fill (wave 2)

- **Files:** apps/api/app/services/content_translation_service.py, apps/api/tests/services/test_content_translation_service.py
- **Action:** `ContentTranslationService(session, translator: Callable[[list[str], str], list[str]] | None = None)`.
  `localize(entity_type, items: Sequence[BaseModel], fields: Sequence[str], language) -> list[BaseModel]`:
  `normalize(language)`; if default → return items unchanged (same objects). Else `repo.get_many`,
  overlay via `model_copy(update=...)`, collect misses `(entity_id, field, source_text)`, and if any:
  one translator call with the full list (default translator = `get_agent_llm("extract_memory")
  .with_structured_output(TranslationBatch)` where `TranslationBatch(items: list[str])`; prompt names
  the target via `LANGUAGE_NAMES`, keeps proper nouns, returns same count/order). Validate count;
  on any exception or count mismatch log `[CONTENT_I18N]` and keep source text. Write back hits
  with `source="llm"` via `upsert_many` (never raise on write failure). Tests with a fake translator
  and with FakeLLM `structured_responses`: overlay, single batched call, second call zero calls,
  default-language no-op returns same objects, failure keeps English, count-mismatch keeps English.
- **Verify:** `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/t21.db ../../.venv/bin/python -m pytest tests/services/test_content_translation_service.py -q`
- **Done:** all six behaviors tested green
- **Criteria:** SC-3
- **Interfaces:** Consumes: `apps/api/app/repositories/content_translation.py`, `apps/api/app/core/languages.py`, and the existing get_agent_llm. Produces: `apps/api/app/services/content_translation_service.py` (`ContentTranslationService.localize`, `TranslationBatch`).

### Task 3.1 — `search_places` localizes at tool time (wave 3)

- **Files:** apps/api/app/tools/place_tools.py, apps/api/tests/tools/test_place_tools_language.py
- **Action:** Add `language: Annotated[str, InjectedState("language")] = Field(default="", description="Injected — never supplied by the model.")`
  to `SearchPlacesArgs` and the matching parameter (default `""`) to `search_places` (pattern:
  `resolve_place.user_id`). After `svc.search_places(...)` and the cap, run
  `ContentTranslationService(s).localize("place", top_results, ["description"], language)` and build
  the panel from the localized list; the `ground` summary is unchanged (names only). Tests (use
  `tests/tools/conftest.agent_db`, monkeypatch `get_agent_llm` in the service module to a FakeLLM
  with `structured_responses=[TranslationBatch(items=[...])]`): (a) `language="vi"` → panel
  descriptions are the translated strings; (b) second call → FakeLLM structured cursor unchanged
  (zero calls) and same output; (c) no `language` → panel identical to a pre-change fixture;
  (d) tool schema (`search_places.args`) does not expose `language`.
- **Verify:** `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/t31.db ../../.venv/bin/python -m pytest tests/tools/test_place_tools_language.py tests/tools/test_place_tools.py -q`
- **Done:** four behaviors green, existing place tool tests green
- **Criteria:** SC-4
- **Interfaces:** Consumes: `apps/api/app/services/content_translation_service.py` and LangGraph InjectedState (existing). Produces: `apps/api/app/tools/place_tools.py` (language-aware `search_places`).

### Task 3.2 — Hotel tools: deferred, verified unchanged (wave 3)

- **Files:** apps/api/tests/tools/test_hotel_tools.py
- **Action:** DEFERRED by decision during execution (SUMMARY § Deviations): the hotels panel
  has no free-form text (`HotelsPanelHotel` and `HotelsPanel.tsx` both omit `description`), so
  localizing it at tool time would spend LLM calls on text nobody sees. The store, service and
  seed already accept `entity_type="hotel"`; wire `language` into `SearchHotelsArgs` /
  `BrowseHotelsArgs` (pattern: Task 3.1) once the hotel panel shows a description. This task
  only re-runs the existing hotel tool tests to prove nothing changed.
- **Verify:** `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/t32.db ../../.venv/bin/python -m pytest tests/tools/test_hotel_tools.py -q`
- **Done:** hotel tool tests green; no hotel tool file touched
- **Criteria:** SC-5
- **Interfaces:** Consumes: existing hotel tool tests. Produces: `apps/api/tests/tools/test_hotel_tools.py` (unchanged, re-run as proof).

### Task 3.3 — Remove the SSE-side translator; panels keep bounded swaps (wave 3)

- **Files:** apps/api/app/streaming/panels/base.py, apps/api/app/streaming/panels/places.py, apps/api/app/streaming/panels/hotels.py, apps/api/app/streaming/panel_localizer.py, apps/api/app/streaming/mapper.py, apps/api/app/agents/graph.py, apps/api/tests/streaming/test_panel_localizer.py, apps/api/tests/streaming/test_mapper_language.py, apps/api/tests/streaming/test_panel_language_e2e.py, apps/api/tests/agents/test_graph_translate_handle.py
- **Action:** Drop the `Translator` type and `translator` parameter from `PanelSpec.localize_vi`,
  `localize_panel`, and each `_localize_vi` (places no longer touches `description`; hotels
  unchanged apart from the signature). Remove `_TRANSLATE_SYSTEM`, `_tl`/`translator` from
  `mapper.py` and `compiled.translate_llm` from `graph.py`. Update the four test modules: keep
  every bounded-swap and language-tag assertion; replace translator assertions with "description
  passes through untouched"; `test_graph_translate_handle.py` becomes an assertion that the
  attribute is absent (or delete the file if it tested only that — say which in the summary).
- **Verify:** `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/t33.db ../../.venv/bin/python -m pytest tests/streaming tests/agents/test_graph_translate_handle.py tests/api/agent/test_stream_events.py -q`
- **Done:** no LLM handle on the SSE path; streaming tests green
- **Criteria:** SC-6
- **Interfaces:** Consumes: nothing new. Produces: `apps/api/app/streaming/panel_localizer.py` (`localize_panel(kind, data, language)`), `apps/api/app/streaming/mapper.py` (translator-free).

### Task 4.1 — Seed pre-fill + one-off generator script (wave 4)

- **Files:** apps/api/app/db/seed.py, apps/api/app/data/content_translations.vi.json, apps/api/scripts/generate_translations.py, apps/api/tests/db/test_seed_translations.py
- **Action:** `seed_all` gains `_seed_content_translations(session)` that loads
  `app/data/content_translations.vi.json` (shape: `[{"entity_type","entity_id","field","text"}]`,
  language implied by filename; file may be `[]`) and upserts rows with `source="seed"`
  (idempotent). `scripts/generate_translations.py --language vi` walks seeded places + hotels,
  calls `ContentTranslationService.localize` against the configured LLM in batches, and writes the
  JSON sorted by (entity_type, entity_id) — running it needs a real key and is a documented manual
  step in the SUMMARY, not a Verify. Test: temp JSON with two rows → rows present after `seed_all`,
  re-run leaves two; generator with a fake translator writes the expected shape.
- **Verify:** `cd apps/api && OPENAI_API_KEY= DATABASE_URL=sqlite:///$(mktemp -d)/t41.db ../../.venv/bin/python -m pytest tests/db/test_seed_translations.py tests/db/test_seed.py -q`
- **Done:** seed idempotent with translations; generator shape-tested
- **Criteria:** SC-7
- **Interfaces:** Consumes: `apps/api/app/repositories/content_translation.py`, `apps/api/app/services/content_translation_service.py`. Produces: `apps/api/app/data/content_translations.vi.json`, `apps/api/scripts/generate_translations.py`.

## 5. Risks

- Double translation if 3.1/3.2 land without 3.3 → same wave, shipped together.
- `agent_db` fixture uses `create_all`, so tests never exercise the migration except SC-2.
- Docker Postgres: `alembic upgrade head` must run before the tool writes rows (documented in
  SUMMARY; `make up` already runs migrations if the entrypoint does — verify in 1.2 summary).
- Generated `vi` text quality is unreviewed; the file is data and can be hand-edited.

## 6. Status Log

- 2026-09-05 — plan written after design approval.
- 2026-09-05 — waves 1–4 implemented directly (single session); Task 3.2 deferred (hotel panel carries no description). `make test` 2120 passed / 5 pre-existing env failures.
