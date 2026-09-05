# catalog-content-i18n — Design

## Problem

Catalog text (place/hotel `description`, later `tags`, `opening_hours` notes…) is seeded in
English only. When the conversation language is `vi`, `app/streaming/panel_localizer.py` swaps
bounded fields via lookup tables (`CATEGORY_VI`, hotel amenities) and sends every free-form
`description` to an LLM translator **per emission** — 4 calls per places panel, every search,
forever, for text that never changes. Language codes are also string literals scattered over
`supervisor.py`, `state.py`, `panel_localizer.py`, `events.py`, `mapper.py`, while the FE owns
its own list in `apps/web/src/i18n/config.ts` (`["en","vi"]`).

## Goals

1. Zero repeated LLM translation for unchanged catalog text (durable cache).
2. Catalog entities can carry text in several languages, extensible to new entities/fields
   without schema churn per language.
3. One source of truth for the supported-language list on the BE, parity-tested against the FE.
4. Fetching a localized entity is one indexed query, not N calls.

## Non-goals

- Translating the agent's own prose (already handled by `with_reply_language`).
- Localizing user-generated content (trips, journal, expenses).
- A CMS/admin UI for editing translations.

## Options — where translations live

| | A. `content_translations` table (recommended) | B. per-language columns (`description_vi`) | C. JSON column `translations` on each entity |
|---|---|---|---|
| Multi-language | any language = a row | new column per language × field × table | any |
| Cache semantics | row = cached translation (`source: seed \| llm`) | no natural miss/fill path | same as A but no index |
| Query cost | 1 extra `IN (ids) AND language=?` on a unique index | 0 extra (same row) | 0 extra, but JSON path filters are dialect-specific (SQLite vs Postgres) |
| Schema churn | one migration, ever | one per language/field | one |
| Risk to existing data | none (additive table) | additive columns, nullable | additive |
| Downsides | one join/second query per panel | explodes with languages; NULL sprawl | no unique constraint per (field, lang); SQLAlchemy JSON dirty-tracking gotchas |

**Recommend A.** It is the only option where "cache" and "multiple versions" are the same
row, and a new language is data, not DDL.

```
content_translations
  id            uuid pk
  entity_type   text   -- "place" | "hotel"  (enum-ish, validated in service)
  entity_id     text   -- fk-less by design (entities live in different tables)
  field         text   -- "description"
  language      text   -- from app.core.languages.SUPPORTED_LANGUAGES
  text          text
  source        text   -- "seed" | "llm"
  updated_at    timestamptz
  UNIQUE (entity_type, entity_id, field, language)
```

Source language (`en`) stays on the entity row; only non-default languages get rows.

## Options — where localization runs

**1. At tool time (recommended).** `search_places` / `browse_hotels` receive
`language: Annotated[str, InjectedState("language")]` (same pattern as `resolve_place`'s
`user_id`; schema-declared so ToolNode still injects — see
`docs/solutions/agent/explicit-args-schema-breaks-tool-injection.md`). The service does
`search(...)` then one `ContentTranslationRepo.get_many(entity_type, ids, fields, language)`
and overlays the text. On a miss it calls the translator, writes the row (`source="llm"`),
and returns. The panel artifact is therefore already localized; `panel_localizer` keeps only
the bounded swaps (category, amenities) and drops the `translator` plumbing.

- + the model reads the same text the traveller sees (today it grounds on English while the
  drawer shows Vietnamese)
- + the tool already owns a `session_scope`; no session plumbing into the SSE generator
- + MCP callers get `language` absent → default `en` → untouched behavior
- − a cold miss adds one LLM round-trip inside the tool (bounded: once per entity/field/lang,
  then never again; pre-seeding removes it entirely)

**2. At stream time (status quo location).** Keep `panel_localizer` but give it a store via
the router's `_isolated_factory`. Less movement, but the mapper grows DB writes, the model
still sees English, and the SSE path keeps an LLM dependency.

**Recommend 1.**

## Language constant (single source of truth)

New `app/core/languages.py`:

```python
SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "vi")
DEFAULT_LANGUAGE = "en"
Language = Literal["en", "vi"]
def normalize(code: str | None) -> str   # unknown/empty → DEFAULT_LANGUAGE
```

Consumers to migrate from literals: `supervisor.py` (default + prompt text listing the
codes), `state.py` type comment, `events.py` defaults, `mapper.py` seed, `panel_localizer.py`
(`if language != "vi"` → `if language == DEFAULT_LANGUAGE`), the new repo/service, and the
translator system prompt (target language name derived from the code, not hardcoded
"Vietnamese"). Parity test: `SUPPORTED_LANGUAGES` == the FE `locales` array (read
`apps/web/src/i18n/config.ts` in a test, like the existing `CATEGORY_VI` ↔ `CATEGORY_META`
parity test).

## Query shape ("đúng data và nhanh nhất")

`PlaceService.search_places(..., language=)`:
1. existing search query → `places` (already capped/sorted)
2. if `language != DEFAULT_LANGUAGE`: one `SELECT … WHERE entity_type='place' AND
   entity_id IN (:ids) AND field IN ('description') AND language=:lang` — unique-index hit,
   ≤ 4 ids for the panel
3. overlay; collect misses; translate misses in **one** batched LLM call (list in → list out)
   and upsert; never block on a translator failure (log, keep English — matches today's
   fail-open in `_localize_vi`).

Seed: `make seed` gains an optional `--translations vi` pass that pre-fills rows from a
checked-in `seed/translations.vi.json` (hand-curated or generated once); with it, prod never
calls the translator for seeded entities.

## Phasing

| Phase | Scope | Gate |
|---|---|---|
| 1 | `app/core/languages.py` + replace literals + FE parity test | none (no schema) |
| 2 | migration + model + repo + service overlay + tool `language` injection + batched miss-fill; `panel_localizer` reduced to bounded swaps; tests (tool-level with FakeLLM translator, repo-level, cold-miss writes once) | **data-loss/migration hard gate** — this approval |
| 3 | seed pre-fill for `vi`; extend to hotels (`description`) | none |

## Open questions for approval

1. Storage: **A** (table) vs B/C?
2. Localization site: **tool time** vs stream time?
3. Miss-fill: translate-on-miss with write-back (recommended) vs seed-only (no runtime LLM at all, English fallback on gaps)?
4. Scope of phase 2: places only, or places + hotels together?

## Decisions (user, 2026-09-05)

1. Storage: **A** — `content_translations` table.
2. Localization site: **tool time** via `InjectedState("language")`.
3. Miss path: **batched translate-on-miss with write-back**; translator failure keeps English.
4. Phase 2 scope: **places + hotels together** (one migration, both tools).

Hard gate `data-loss/migration` narrowed by the user to an additive table only (no existing
column touched); approval recorded here — proceed to xia2 → writing-plans.
