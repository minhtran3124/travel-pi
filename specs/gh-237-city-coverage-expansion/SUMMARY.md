# gh-237-city-coverage-expansion — Summary

Lane: normal
Confidence: high
Reason: seed-data expansion across several data modules (existing behavior, multi-domain, weak proof). No hard gate: no schema change or migration (seed_all upserts with session.merge), no auth or public-contract change, and no new runtime dependency.
Flags: existing behavior, multi-domain, weak proof
Affects: apps/api/app/data/{cities,airports,hotels,places,tips,visa,countries,fx}.py, app/data/content_translations.vi.json; the synthetic flight and hotel services that read them; eval goldens and baselines that depend on seed data
Input-type: new initiative
Route: xia2 (Standard) → writing-plans → using-git-worktrees → subagent-driven-development
Escalate: no

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> Có thể check xem thành phố nào ko có trong dữ liệu thì cập nhật thêm. Tìm nguồn internet latest và update.

(Scope chosen by the user in answer to the follow-up questions: "Đông Bắc Á + quốc tế phổ biến" — about 20 cities: Osaka, Kyoto, Fukuoka, Sapporo, Busan, Jeju, Taipei, Shanghai, Beijing, Guangzhou, Paris, London, Lisbon, Rome, Sydney, Melbourne, Dubai, Istanbul, New York, Los Angeles; depth "Đầy đủ" — airports and routes, 6–8 real hotels, places, tips, visa/fx for new countries, and Vietnamese translations.)

> Nếu cần thì spawn subagent với haiku để tìm kiếm cho rẻ

## What changed

20 destination cities (Osaka, Kyoto, Fukuoka, Sapporo, Busan, Jeju, Taipei, Shanghai, Beijing, Guangzhou, Paris, London, Lisbon, Rome, Sydney, Melbourne, Dubai, Istanbul, New York, Los Angeles) join the seed catalogue: 10 countries with visa, fx and 6 sourced tips each, 27 airports, 156 hotels, 183 places, 75 city tips and 339 Vietnamese descriptions. Every hotel and place is a Wikidata item with its own coordinates and a Commons image (or the city landmark image, marked in provenance).

Pipeline (all reproducible, under `apps/api/scripts/`): `fetch_city_candidates.py` (Wikidata SPARQL, Commons, Wikipedia REST, Wikivoyage; commands in `candidates/FETCH.md`) → Haiku picks by QID in `selections/<city>.json`, citing digest sentence ids → `build_city_sources.py` copies facts from the candidates and blocks unsourced numbers, closure wording, unrelated tip evidence, under-priced stars and unlocalised amenities → `check_seed_sources.py` (offline + `--online`: QID exists, coordinates within 1 km of any P625, image loads) → `import_seed_sources.py` appends marked blocks to `app/data/*.py`.

Runtime fixes the new data made necessary (user-approved 2026-09-26):
- Fuzzy name matching (`app/core/text.py`): the score is the best of all rules; difflib needs the same first letter, a candidate of 4+ characters and a ratio ≥ 0.75; a substring hit needs 3 characters at a word start; all-tokens-prefix, collapsed-prefix, contained-name (longer name first) and "<name>, …" rules keep partial and "City, Country" input working; country aliases (US/UK/Britain/UAE/Türkiye…) resolve first. Stops "US"→Australia, "Britain"→Taiwan, "Sapa"→Osaka, "Porto"→Sapporo, "Hangzhou"→Guangzhou, "USA"→Busan, and fixes the pre-existing "Saigon"→Yangon.
- Long-haul flights (`flight_service.py`): routes over 4,500 km derive duration and price from distance after the same RNG draws, so existing short-haul flights and the determinism golden are unchanged (HAN→JFK now ~17h; fares start from the drawn short-haul fare at 4,500 km and add 8% per stop).
- Geocoding (`weather_service.geocode_city`): a seeded city uses its seeded coordinates ("Jeju" no longer resolves to Ethiopia).
- RAG startup (`lifespan.py`): re-ingests when the store's document count differs from the corpus, so new visa/tips prose reaches an existing Postgres store.
- `AMENITY_VI` gains "Hot Spring".

### Rationale

Both live user-simulation runs sent travellers to cities outside the 52-city inventory (Osaka, Lisbon), and the agent looped on empty searches (#237). Expanding the inventory in the existing seed format fixes the gap without any code or schema change. Web research runs on Haiku subagents to keep cost down, and the stronger model assembles and verifies the data.

### Alternatives considered

- Fix the agent behaviour first (#237) — still needed, and kept separate. The user asked for data coverage here.
- A live hotel/places provider — out of scope. Inventory stays synthetic by design (AGENTS.md).

### Deviations

- Plan gap: free-form Haiku web research fabricated data (0/118 real images, the Reims cathedral in Paris). Replaced by the deterministic candidate fetcher (Task 1.3) and pick-by-QID curation.
- Plan gap: Haiku curation still passed checks while picking closed or misplaced items (Cecil Hotel, Windows on the World, Foshan Hotel, a café closed in 2025, a QID carrying another restaurant's text) and citing unrelated tip sentences. Two Sonnet review passes replaced ~30 picks; the builder now blocks those patterns.
- Scope cut: the 11 new airlines are not imported. `generate_flights` draws `rng.choice` over the whole `AIRLINES` list, so any addition re-assigns the airline of every existing flight. They stay in `foundations.json` under `airlines_not_imported`; new routes use the existing 7 carriers.
- Convention correction: `visa.py` is generic ("many passports"); new entries add one sentence for Vietnamese passport holders. Japan and South Korea are unchanged.
- Rule 1: `hotels.chain` is NOT NULL — brand names map to the parent group already used in the catalogue, else "Independent" (`import_seed_sources.py`).
- Rule 1: tightened fuzzy matching and the three runtime fixes above came from the final correctness review; the user chose the approach for each. Two re-review rounds then restored recall the first tightening lost (interior fragments, "City, Country", 3-letter syllables, one-typo names) and fixed early-return score capping.
- Imperial Hotel, Osaka was dropped: its star class had no source, and Osaka needed a genuine budget hotel (Hotel Kintetsu Universal City) within the 6–8 range.
- Issue #238 opened for the pre-existing duplicate Cebu hotel (CEB001/CEB002); the uniqueness test exempts that pair by name.

### Advisory (recorded, not fixed)

- Addresses come from Wikidata (English street address, else "<district>, <city>", skipping a district that is the city itself or an admin level above it); 42 of 156 new hotels and 79 of 183 new places show only the city because Wikidata has no usable district.
- Departure/arrival boards (`board_service`) sample from the whole airport list, so existing boards show a different route set now that there are 76 airports.
- `KIX`/`ITM` belong to Osaka; Kyoto lists them as its airports (no runtime reverse lookup today).
- An expense edited after the fx refresh is re-converted at the new rate (pre-existing logic).
- "Austria" still fuzzy-matches "Australia" (same first letter, ratio 0.875); "Hue Vietnam" without a comma does not match Hue.
- Long-haul `arrival_time` adds the flight duration to the local departure time without a timezone offset (pre-existing; now visible on overnight routes).
- The RAG startup probe checks that every corpus id exists; a tip whose text changes under the same id is not re-embedded (pre-existing upsert-only ingest).
- 37 of 156 new hotels use the city landmark image (no Commons image of the property).
- Stale RAG documents are never purged (upsert-only ingest, pre-existing).
- `eval/datasets/web_search.json` case about Paris strikes may now reach catalogue tools first; eval not run.

### Verify

Run from the worktree root (`.venv` → the repo venv); `DATABASE_URL=sqlite:///./test.db`.

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| modules import with validators | `.venv/bin/python -c "import sys; sys.path.insert(0,'apps/api'); import app.data.countries, app.data.cities, app.data.airports, app.data.airlines, app.data.hotels, app.data.places, app.data.tips, app.data.visa, app.data.fx"` | 0 | | SC-1 |
| provenance checks | `.venv/bin/python apps/api/scripts/check_seed_sources.py specs/gh-237-city-coverage-expansion/sources --require-cities` | 0 | OK 8 files; `--online` also exit 0 | SC-2 |
| coverage incl. vi | `.venv/bin/python -m pytest apps/api/tests/data/test_city_coverage.py -q` | 0 | 140 passed | SC-3 |
| full-catalogue seed | `.venv/bin/python -m pytest apps/api/tests/data/test_seed_full_catalog.py -q` | 0 | 45 passed | SC-4 |
| search per new city | `.venv/bin/python -m pytest apps/api/tests/data/test_new_city_search.py -q` | 0 | 60 passed | SC-5 |
| reference repos | `.venv/bin/python -m pytest apps/api/tests/repositories/test_reference_repos.py -q` | 0 | 35 passed | SC-6 |
| lint | `.venv/bin/ruff check apps/api/app/data apps/api/scripts/check_seed_sources.py apps/api/tests/data` | 0 | | SC-7 |
| builder gates | `cd apps/api && ../../.venv/bin/python -m scripts.build_city_sources --check` | 0 | 0 errors | |

Full backend suite (≈6 min, over the 60 s row limit): `cd apps/api && DATABASE_URL=sqlite:///./test.db ../../.venv/bin/python -m pytest -q -p no:cacheprovider` → exit 0, 3496 passed, 9 skipped (2026-09-26, at e3286d71).

### Not auto-verified

- Truth of web-sourced facts beyond what the checks prove: QIDs, coordinates (≤1 km of Wikidata), images (load) and quoted evidence are verified; indicative prices, ratings, review counts, opening hours and star classes are curated values, reviewed by two Sonnet passes, not proven.
- `make test-docker` (Postgres) was not run: it tears down the shared dev stack. No schema change; seeding is `session.merge`.
- The agent eval (`make eval-smoke` / `eval-check`) was not run; the fuzzy-matching change and the new catalogue can move judged scores.
- The RAG re-ingest on an existing Postgres store is covered by a fake-store test, not a live run.

### Rollback

- `git revert <merge sha>` restores code and data. Rows already upserted by `seed_all` (new cities, hotels, places, tips) stay in an existing DB until it is reseeded; RAG vectors for the new prose stay until the collection is rebuilt (`python scripts/ingest_rag.py` after reverting).

### Harness-Delta

- none
