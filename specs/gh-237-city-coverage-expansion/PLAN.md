---
slug: gh-237-city-coverage-expansion
status: active
owner: Minh Tran
created: 2026-09-26
---

# City coverage expansion — 20 destinations with full seed depth

Inputs: `SUMMARY.md` (intake, normal), `research-brief.md` (Standard). Paths are relative to the repo root.

## 1. Motivation

The synthetic inventory covers 52 cities: Southeast Asia plus Tokyo, Seoul and Hong Kong. Both
live user-simulation runs sent travellers elsewhere (Osaka, Lisbon), and the agent looped on empty
searches (#237). This plan adds 20 high-demand destinations at full depth:

- **Northeast Asia:** Osaka, Kyoto, Fukuoka, Sapporo, Busan, Jeju, Taipei, Shanghai, Beijing, Guangzhou
- **International:** Paris, London, Lisbon, Rome, Sydney, Melbourne, Dubai, Istanbul, New York, Los Angeles

Full depth means airports, 6–8 real hotels, 8 or more places, tips, visa/fx for the 10 new
countries, and vi translations. The data comes from current web sources.

## 2. Non-goals

- No live price or availability provider; inventory stays synthetic (AGENTS.md).
- No change to services, schema, seed code or agent prompts. Fixing the #237 agent behaviour is separate.
- No new eval goldens.

## Global Constraints

- **Source discipline.**
  - Every web-sourced record carries a `source_url` in the region's provenance JSON under `specs/gh-237-city-coverage-expansion/sources/`.
  - Facts come from en.wikipedia.org / wikivoyage.org / commons.wikimedia.org. FX comes from the ECB euro reference rates, all on one date recorded in `fx.LAST_UPDATED`. Visa entries follow the existing `visa.py` convention: `visa_free_days` and the flags describe the common "many passports" case, the concierge prompt already tells travellers to confirm for their nationality, and each summary adds one sentence for Vietnamese passport holders plus the check date. The existing Japan and South Korea entries stay unchanged.
  - Hotel names, addresses and images must be real. `image_url` must be an `https://upload.wikimedia.org/` URL. If no Commons image exists, reuse the city's landmark image and say so in provenance.
- **Indicative values.** `price_per_night` (USD), `rating`, `review_count`, `price_level` and `opening_hours` are indicative snapshot values, the same convention as the existing 188 hotels.
  - Price bands follow star class and city cost level.
  - Each city has at least 2 hotels at or under $130/night and at least 2 hotels of 4★ or above.
- **Candidates first, then Haiku curation.**
  - Hotels, places and their coordinates and images come only from the deterministic fetcher (`scripts/fetch_city_candidates.py`, Task 1.3), which reads Wikidata SPARQL, the Wikipedia REST summaries and Wikivoyage wikitext.
  - Haiku subagents (user request, for cost) only *select* from a city's candidate file and write short descriptions and tips from the fetched text. They never add a record, name, coordinate or image of their own.
  - Every hotel and place carries its `wikidata` QID.
  - `scripts/check_seed_sources.py --online` verifies each QID exists, that the record's coordinates are within 1 km of the QID's P625, and that `image_url` loads (HTTP 200 or 206).
  - Assembly, validation and review run on a stronger model.
  - **Why:** the first free-form Haiku attempt returned 0 real images out of 118 and misplaced a Reims cathedral in Paris (2026-09-26).
- **Module conventions.**
  - Append only, never insert: `AIRLINES` order is load-bearing, and tip ids depend on position.
  - New hotel `id` = `deterministic_uuid("hotel", code)`; new place `id` = `deterministic_uuid("place", city, name)` (from `app/db/base.py`).
  - Hotel `code` = the city's primary IATA code plus a 3-digit sequence (KIX001…). A city with no airport of its own uses its IATA metropolitan city code (Kyoto → `UKY`). Every other city uses its real airport code (Jeju → `CJU`, Osaka → `KIX`).
  - `description` follows the existing template sentence style.
  - Existing rows are unchanged.
- **Coverage per new city:**
  - 1 or more airport codes;
  - 6–8 hotels (at least 2 under $130, at least 2 of 4★+);
  - 8 or more places (at least 5 attractions, at least 2 restaurants or cafes);
  - 3 or more `CITY_TIPS`;
  - its country present in `COUNTRIES`, `COUNTRY_VISA`, `COUNTRY_CURRENCY`/`RATES`, `COUNTRY_TIPS` and `COUNTRY_SUMMARIES`;
  - a vi `description` row for every new hotel and place.
- **Sanity rules** (enforced by the check script):
  - coordinates within valid ranges and within 60 km of the city centre (airports within 80 km);
  - no duplicate ids, codes, or (city, name) pairs;
  - stars 1–5; rating 1–5; price > 0.
- **Paths.**
  - Python from `apps/api/`, with the root `.venv`.
  - Tests in `apps/api/tests/data/`.
  - `ruff check` and `ruff format` clean on touched Python.

## 3. Success Criteria

| ID | Behavior (observable) | Check (re-runnable) | Expected |
|------|-------------------------|-----------------------|------------|
| SC-1 | Every data module imports with its validators passing | `.venv/bin/python -c "import sys; sys.path.insert(0,'apps/api'); import app.data.countries, app.data.cities, app.data.airports, app.data.airlines, app.data.hotels, app.data.places, app.data.tips, app.data.visa, app.data.fx"` | exit 0 |
| SC-2 | Each provenance file passes the source sanity checks | `.venv/bin/python apps/api/scripts/check_seed_sources.py specs/gh-237-city-coverage-expansion/sources --require-cities` | exit 0 |
| SC-3 | All 20 new cities meet the coverage rules, including vi translations | `.venv/bin/python -m pytest apps/api/tests/data/test_city_coverage.py -q` | exit 0 |
| SC-4 | A fresh SQLite seed of the full catalog succeeds, including the short_code collision check | `.venv/bin/python -m pytest apps/api/tests/data/test_seed_full_catalog.py -q` | exit 0 |
| SC-5 | Hotel search, flight search and places lookup return results for every new city | `.venv/bin/python -m pytest apps/api/tests/data/test_new_city_search.py -q` | exit 0 |
| SC-6 | Existing reference-repository tests still pass | `.venv/bin/python -m pytest apps/api/tests/repositories/test_reference_repos.py -q` | exit 0 |
| SC-7 | Touched Python is lint-clean | `.venv/bin/ruff check apps/api/app/data apps/api/scripts/check_seed_sources.py apps/api/tests/data` | exit 0 |

## 4. Tasks

### Task 1.1 — Foundations: countries, visa, fx, airlines, airports (wave 1)

- **Files:** apps/api/app/data/countries.py, apps/api/app/data/visa.py, apps/api/app/data/fx.py, apps/api/app/data/airlines.py, apps/api/app/data/airports.py, specs/gh-237-city-coverage-expansion/sources/foundations.json
- **Action:**
  - Dispatch one Haiku subagent to research, with a `source_url` per record:
    - ISO2 code, region label and centroid for China, Taiwan, France, United Kingdom, Portugal, Italy, Australia, United Arab Emirates, Turkey and United States;
    - the visa rules for those countries, in the existing generic convention, with a sentence for Vietnamese passport holders;
    - IATA code, official name and coordinates for the airports: KIX, ITM, FUK, CTS, PUS, CJU, TPE, TSA, PVG, SHA, PEK, PKX, CAN, CDG, ORY, LHR, LGW, LIS, FCO, SYD, MEL, DXB, IST, SAW, JFK, EWR, LAX;
    - 10–12 major carriers for those markets.
  - Save the findings to `sources/foundations.json`.
  - Fetch the ECB euro reference rates for the latest date yourself, not via Haiku. Convert them to units per 1 USD, then refresh ALL existing rates to that date and add CNY, TWD, EUR, GBP, AUD, AED, TRY and USD mappings.
  - Append the entries to the modules following their existing conventions. Carriers are appended at the end of `AIRLINES`, with colours.
- **Verify:** `.venv/bin/python -c "import sys; sys.path.insert(0,'apps/api'); import app.data.visa, app.data.fx, app.data.airports, app.data.airlines"`
- **Done:** The 10 new countries are in `COUNTRIES`, `COUNTRY_VISA` and `COUNTRY_CURRENCY`. `fx.LAST_UPDATED` equals the ECB date. The 27 airport codes are in `AIRPORTS`. The import exits 0.
- **Criteria:** SC-1
- **Interfaces:** Consumes the ECB euro FX reference XML and Wikipedia pages. Produces `sources/foundations.json` and the updated `app/data/{countries,visa,fx,airlines,airports}.py`.

### Task 1.2 — Source sanity checker and coverage tests (wave 1)

- **Files:** apps/api/scripts/check_seed_sources.py, apps/api/tests/data/test_check_seed_sources.py, apps/api/tests/data/test_city_coverage.py, apps/api/tests/data/test_seed_full_catalog.py, apps/api/tests/data/test_new_city_search.py
- **Action:** Write the tests first.
  - `check_seed_sources.py <dir>` validates every `*.json` provenance file against the shapes in Task 2.x: required keys, coordinate ranges, distance from the city centre (haversine, 60 km, or 80 km for airports), duplicate names, star/rating/price ranges, `https://upload.wikimedia.org/` images, and a `source_url` on every record. It prints one line per violation and exits 1 on any violation, 0 otherwise.
  - `test_city_coverage.py` is parametrized over the 20 new cities and asserts the Global Constraints coverage rules. It checks airport codes exist in `AIRPORTS`; 6–8 hotels with at least 2 under $130 and at least 2 of 4★+; 8 or more places with at least 5 attractions and at least 2 restaurants or cafes; 3 or more `CITY_TIPS`; the country in visa/fx/tips/summaries; and vi description rows for every hotel and place id. It follows the style of `tests/data/test_phu_quoc_inventory.py`.
  - `test_seed_full_catalog.py` runs `seed_all` on a temp SQLite file and asserts that it completes (including `_check_short_code_collisions`) and that the new cities' hotel/place row counts match the data modules.
  - `test_new_city_search.py` uses the seeded temp DB and the real services/repositories. For each new city it asserts that hotel search for a date range returns 1 or more available hotels, that flight search HAN → its primary airport returns 1 or more flights, and that places by city returns 8 or more.
  - `test_check_seed_sources.py` imports the checker and asserts that its built-in good record passes and that its bad records fail, including an impossible coordinate such as 34°65′, a non-Commons image, and a missing `source_url`.
  - The coverage, seed and search tests fail until waves 3–5; record the expected red state in the report.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/data/test_check_seed_sources.py -q`
- **Done:** `test_check_seed_sources.py` passes: the good record is accepted, and each bad record is rejected with a violation line.
- **Criteria:** SC-2, SC-3, SC-4, SC-5
- **Interfaces:** Consumes the app/data module shapes. Produces `apps/api/scripts/check_seed_sources.py`, `apps/api/tests/data/test_check_seed_sources.py`, `apps/api/tests/data/test_city_coverage.py`, `test_seed_full_catalog.py` and `test_new_city_search.py`.

### Task 1.3 — Candidate fetcher and online verification (wave 1b)

- **Files:** apps/api/scripts/fetch_city_candidates.py, apps/api/scripts/check_seed_sources.py, apps/api/tests/data/test_check_seed_sources.py, specs/gh-237-city-coverage-expansion/candidates/.gitkeep
- **Action:** Runs after Task 1.2.
  - `fetch_city_candidates.py <city> <wikidata-QID> [--out DIR]` writes `candidates/<city>.json` with:
    - `hotels`: up to 40 items, instance of hotel, hostel or capsule hotel (subclasses included), located in the city (P131 chain), with QID, label, P625, P18 resolved to an `upload.wikimedia.org` URL through the Commons imageinfo API, address (P6375, otherwise the P131 district label), and sitelinks;
    - `places`: up to 60 items, the most-linked items in the city with coordinates and an image, excluding people, companies, administrative areas and stations, each with its instance-of labels;
    - `restaurants`: items that are restaurants or cafés in the city;
    - `wikipedia`: summary extracts for each candidate;
    - `wikivoyage`: the city page's plain-text sections Get around, Stay safe, Eat and Sleep.

    It sends a descriptive User-Agent, retries politely, and sleeps 1 s between SPARQL calls.
  - Extend `check_seed_sources.py` with `--online`. For every hotel and place, the `wikidata` QID must exist, the record's coordinates must lie within 1 km of that QID's P625, and `image_url` must return 200 or 206 on a ranged GET with the same User-Agent. The offline mode also requires a `wikidata` field matching `Q\d+`.
  - Add a unit test for the offline `wikidata` rule. The online checks are exercised by the wave 2 verify commands.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/data/test_check_seed_sources.py -q`
- **Done:** The test passes. Running `fetch_city_candidates.py Osaka Q35765` writes a candidates file with 10 or more hotels and 20 or more places, each with a QID and an image URL (recorded in the report).
- **Criteria:** SC-2
- **Interfaces:** Consumes Wikidata SPARQL, the Commons API, the Wikipedia REST API and the Wikivoyage API. Produces `apps/api/scripts/fetch_city_candidates.py` and the `--online` mode of `apps/api/scripts/check_seed_sources.py`.

### Task 2.1 — Research: Japan (wave 2)

- **Files:** specs/gh-237-city-coverage-expansion/sources/japan.json
- **Action:** Run `fetch_city_candidates.py` for Osaka, Kyoto, Fukuoka and Sapporo. Then dispatch Haiku subagents, one per city, that select only from that city's candidate file (keeping each record's `wikidata` QID, coordinates and image unchanged) and return JSON with:
  - `city` (name, country, airport_codes, latitude, longitude, source_url);
  - `hotels[6-8]`, carrying every `hotels.py` field except `id`/`code`, plus `source_url`;
  - `places[8+]`, carrying every `places.py` field except `id`, plus `source_url`;
  - `city_tips[3+]` (category, title, content, is_essential, source_url).

  Merge the results into `japan.json` (a list of city objects) and fix every violation reported by the checker.
- **Verify:** `.venv/bin/python apps/api/scripts/check_seed_sources.py specs/gh-237-city-coverage-expansion/sources/japan.json --online`
- **Done:** 4 cities, each with 6–8 hotels, 8 or more places and 3 or more tips; the checker exits 0.
- **Criteria:** SC-2
- **Interfaces:** Consumes the Wikipedia, Wikivoyage and Commons pages. Produces `sources/japan.json`.

### Task 2.2 — Research: Korea and Taiwan (wave 2)

- **Files:** specs/gh-237-city-coverage-expansion/sources/korea_taiwan.json
- **Action:** Same as Task 2.1 (fetch candidates, then Haiku selection), for Busan, Jeju and Taipei.
- **Verify:** `.venv/bin/python apps/api/scripts/check_seed_sources.py specs/gh-237-city-coverage-expansion/sources/korea_taiwan.json --online`
- **Done:** 3 cities meet the counts; the checker exits 0.
- **Criteria:** SC-2
- **Interfaces:** Consumes the web sources. Produces `sources/korea_taiwan.json`.

### Task 2.3 — Research: China (wave 2)

- **Files:** specs/gh-237-city-coverage-expansion/sources/china.json
- **Action:** Same as Task 2.1 (fetch candidates, then Haiku selection), for Shanghai, Beijing and Guangzhou.
- **Verify:** `.venv/bin/python apps/api/scripts/check_seed_sources.py specs/gh-237-city-coverage-expansion/sources/china.json --online`
- **Done:** 3 cities meet the counts; the checker exits 0.
- **Criteria:** SC-2
- **Interfaces:** Consumes the web sources. Produces `sources/china.json`.

### Task 2.4 — Research: Europe (wave 2)

- **Files:** specs/gh-237-city-coverage-expansion/sources/europe.json
- **Action:** Same as Task 2.1 (fetch candidates, then Haiku selection), for Paris, London, Lisbon and Rome.
- **Verify:** `.venv/bin/python apps/api/scripts/check_seed_sources.py specs/gh-237-city-coverage-expansion/sources/europe.json --online`
- **Done:** 4 cities meet the counts; the checker exits 0.
- **Criteria:** SC-2
- **Interfaces:** Consumes the web sources. Produces `sources/europe.json`.

### Task 2.5 — Research: Oceania, Middle East, Turkey (wave 2)

- **Files:** specs/gh-237-city-coverage-expansion/sources/oceania_me.json
- **Action:** Same as Task 2.1 (fetch candidates, then Haiku selection), for Sydney, Melbourne, Dubai and Istanbul.
- **Verify:** `.venv/bin/python apps/api/scripts/check_seed_sources.py specs/gh-237-city-coverage-expansion/sources/oceania_me.json --online`
- **Done:** 4 cities meet the counts; the checker exits 0.
- **Criteria:** SC-2
- **Interfaces:** Consumes the web sources. Produces `sources/oceania_me.json`.

### Task 2.6 — Research: United States (wave 2)

- **Files:** specs/gh-237-city-coverage-expansion/sources/usa.json
- **Action:** Same as Task 2.1 (fetch candidates, then Haiku selection), for New York and Los Angeles.
- **Verify:** `.venv/bin/python apps/api/scripts/check_seed_sources.py specs/gh-237-city-coverage-expansion/sources/usa.json --online`
- **Done:** 2 cities meet the counts; the checker exits 0.
- **Criteria:** SC-2
- **Interfaces:** Consumes the web sources. Produces `sources/usa.json`.

### Task 2.7 — Research: country tips and summaries for the 10 new countries (wave 2)

- **Files:** specs/gh-237-city-coverage-expansion/sources/countries.json
- **Action:** Dispatch Haiku subagents, one per country, for China, Taiwan, France, United Kingdom, Portugal, Italy, Australia, United Arab Emirates, Turkey and United States. Each returns `{country, summary, summary_source_url, tips: [3+ {category, title, content, is_essential, source_url}]}`. Categories follow the existing `COUNTRY_TIPS` categories in `app/data/tips.py`, and content covers entry, money, transport and etiquette. Merge the results into `countries.json` and run the checker on it.
- **Verify:** `.venv/bin/python apps/api/scripts/check_seed_sources.py specs/gh-237-city-coverage-expansion/sources/countries.json`
- **Done:** 10 countries, each with a summary and 3 or more sourced tips; the checker exits 0.
- **Criteria:** SC-2
- **Interfaces:** Consumes the Wikivoyage country pages. Produces `sources/countries.json`.

### Task 3.1 — Assemble cities, hotels, places and tips into the data modules (wave 3)

- **Files:** apps/api/app/data/cities.py, apps/api/app/data/hotels.py, apps/api/app/data/places.py, apps/api/app/data/tips.py, apps/api/scripts/import_seed_sources.py
- **Action:**
  - Write a one-off, deterministic importer, `scripts/import_seed_sources.py`. It reads `sources/*.json` and renders module entries that follow the conventions in Global Constraints (ids, codes, description template, field order), appended after the existing entries. Nothing is hand-typed.
  - Add `COUNTRY_TIPS` (3 or more each) and `COUNTRY_SUMMARIES` for the 10 new countries from `sources/countries.json`.
  - Add the 20 cities to `CITIES`, and remove any `source_url` from module output.
  - Run the importer, then ruff format.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/data/test_city_coverage.py -q -k "not translations"`
- **Done:** SC-1 import exits 0. Every coverage test except the vi-translation cases passes, and existing rows are byte-identical (`git diff` shows additions only in `app/data/*.py`).
- **Criteria:** SC-1, SC-3, SC-7
- **Interfaces:** Consumes `sources/*.json`, including `sources/countries.json` and `sources/foundations.json`. Produces `apps/api/scripts/import_seed_sources.py` and the updated `app/data/{cities,hotels,places,tips}.py`.

### Task 4.1 — Vietnamese translations for new hotels and places (wave 4)

- **Files:** apps/api/app/data/content_translations.vi.json
- **Action:** For every new hotel and place id, append a `{entity_type, entity_id, field: "description", text}` row with a natural Vietnamese translation. Dispatch Haiku subagents in batches of about 50 descriptions. Each returns `{entity_id: text}`, preserving proper nouns, numbers and star counts. Merge with a script so the file stays valid JSON with existing rows unchanged.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/data/test_city_coverage.py -q`
- **Done:** All coverage tests pass, including translations. The row count increases by exactly the number of new hotels plus places.
- **Criteria:** SC-3
- **Interfaces:** Consumes the new hotel/place ids from the hotels and places modules updated by Task 3.1. Produces the updated `app/data/content_translations.vi.json`.

### Task 4.2 — Full-catalog seed and search checks (wave 5)

- **Files:** apps/api/tests/data/test_seed_full_catalog.py, apps/api/tests/data/test_new_city_search.py
- **Action:** Make SC-4 and SC-5 pass against the assembled data. Fix test fixtures only. A data problem (for example a short_code collision) is reported as BLOCKED with the colliding ids, not patched here.
- **Verify:** `.venv/bin/python -m pytest apps/api/tests/data/test_seed_full_catalog.py apps/api/tests/data/test_new_city_search.py -q`
- **Done:** Both test files pass.
- **Criteria:** SC-4, SC-5, SC-6
- **Interfaces:** Consumes the seed_all repositories and services. Produces the passing `apps/api/tests/data/test_seed_full_catalog.py` and `test_new_city_search.py`.

## 5. Risks

- **Web data errors from Haiku.** Mitigated by the checker (ranges, distance, duplicates), the per-task review, and a spot check of about 10% of records against their source URLs in the final review.
- **short_code collisions** as about 150 hotels and 200 places are added. SC-4 catches them; resolution changes the colliding record's code or name source.
- **Diff size.** The importer script and provenance JSON make the data change reproducible and reviewable by source.
- **Visa and FX staleness.** Both are dated in summaries and `LAST_UPDATED`.

## 6. Status Log

- 2026-09-26 — Waves 1–5 done. Curation moved to a pick-by-QID pipeline: `selections/<city>.json` (Haiku) → `build_city_sources.py` (copies facts from candidates, resolves `wp:`/`wv:` evidence ids, blocks closure wording, unrelated tip evidence and under-priced stars) → `sources/<region>.json` → `import_seed_sources.py` → `app/data`. Two Sonnet review passes replaced ~30 closed, misplaced or mis-cited picks. SC-2 now passes `--require-cities`.
- 2026-09-26 — Wave 2 research was redesigned. The first free-form Haiku pass (Europe, Korea/Taiwan) produced 0/118 real image URLs and a misplaced place, so both files were discarded. Task 1.3 was added (a deterministic Wikidata/Wikipedia/Wikivoyage candidate fetcher plus `--online` verification); Haiku now only selects and describes real candidates.
- 2026-09-26 — plan written (proposed). Plan review found 4 issues, all fixed: Task 2.7 added for country tips and summaries, Task 4.2 moved to wave 5 because seeding reads the translations file, Task 1.2 now verified by a checker test, and the city-code wording clarified.
