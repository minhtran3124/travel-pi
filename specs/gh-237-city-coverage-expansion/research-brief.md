---
slug: gh-237-city-coverage-expansion
doc: research-brief
created: 2026-09-26
depth: Standard (from intake lane normal; no upgrade)
---

# Research Brief — gh-237-city-coverage-expansion

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | Reuse the existing data-module pattern: extend `app/data/*.py` in place, following each module's current conventions, and backfill vi translations with the existing `scripts/generate_translations.py`. Web facts come from Wikipedia and Wikimedia Commons (via Haiku subagents), and FX comes from the ECB reference rates. |
| **Why this is the lightest credible path** | No schema, service or seed code changes. Flights and hotel availability are hash-seeded and region-agnostic, and the import-time validators already enforce integrity. |
| **Confidence** | 80% |
| **Next step** | Write PLAN.md: shared foundations first (countries, visa, fx, airlines, airports), then per-region city batches (cities, hotels, places, tips), then translations, then verification. |

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | Monorepo: FastAPI API plus Next.js web |
| Primary language + runtime | Python 3.14 (local `.venv`) and 3.12 (Docker) |
| Relevant packages | none new; seed via SQLAlchemy `session.merge` |
| Important constraints | Travel inventory stays synthetic (AGENTS.md). Seed upserts, so new rows reach existing DBs on startup. RAG re-ingests from the DB at startup. |

## Feature Understanding and Assumptions

- **Requested:** find the missing destination cities and add them with the latest web sources. The user scoped this to 20 cities at full depth: airports, hotels, places, tips, visa, fx and vi translations.
- **Success means:** each new city is searchable end to end.
  - `search_flights` to and from its airport returns flights.
  - `search_hotels` and `browse_hotels` return 6–8 real hotels.
  - Places and tips exist.
  - Visa and fx exist for each new country.
  - Descriptions have vi translations.
  - A user-simulation persona asking for Osaka or Lisbon no longer hits empty results (#237's trigger).
- **Assumptions:**
  - Prices, ratings and review counts are **indicative snapshot values**, as the existing 188 hotels are (for example Park Hyatt Tokyo at $550, 4.8, 3,210 reviews). Live OTA prices are not reachable (see Docs).
  - Visa is keyed by destination country and describes a **Vietnamese passport holder**, as in the existing `visa.py`.

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `countries.py` holds `name`, `code`, `region` (free string, no enum), and lat/long. New countries must be added first, because every other module validates against it at import. |
| `Local` | `cities.py` fields: `name`, `country`, `airport_codes[]`, lat/long. The validator is at `cities.py:372-379`. |
| `Local` | `airports.py` is a `AIRPORTS: dict[iata → {name, city, country}]`; `country_code` is auto-filled, and an unknown country raises KeyError (`:253-257`). |
| `Local` | `hotels.py` schema has 20 fields. `id` is a UUID5 of the slug, precomputed with no helper. `code` is the IATA/city prefix plus a sequence (`DAD001`). The file enforces at least 3 hotels per city (`:382-395`). |
| `Local` | `places.py` carries `id` (UUID5), name, city, country, category, description, address, rating, review_count, price_level, opening_hours, image_url, tags, is_recommended and lat/long. The file enforces at least 3 places per city and checks that each place's country matches its city (`:479-501`). |
| `Local` | `tips.py` has `COUNTRY_TIPS`, `CITY_TIPS` and `COUNTRY_SUMMARIES`; its validator covers only the COUNTRY keys. Tip ids depend on list position, so tips must be appended only, never inserted mid-list (`seed.py:167-186`). |
| `Local` | `visa.py` `COUNTRY_VISA` must cover `COUNTRIES` 1:1, or import fails (`:106-117`). |
| `Local` | `fx.py` holds `RATES` (units per 1 USD), `CURRENCY_NAMES`, `COUNTRY_CURRENCY` and one `LAST_UPDATED`. Its validators require every country to have a currency, every currency a rate, and every rate a name. |
| `Local` | `content_translations.vi.json` is a flat list of `{entity_type: place\|hotel, entity_id, field: description, text}` (701 rows). `scripts/generate_translations.py` fills in the missing rows (it needs an LLM key and a seeded DB). |
| `Local` | Flights (`flight_service.py:57-105`) are hashed on `origin-destination-date`, with a random airline from `AIRLINES` (order is load-bearing: append only), duration 80–360 min and price 50–800. They are region-agnostic. |
| `Local` | Hotel availability (`hotel_service.py:19-51`) is MD5-seeded per hotel and date. |
| `Local` | `seed.py:284-306` runs a `short_code` collision check. Adding about 150 hotels and 200 places raises the collision risk, so verify it by seeding. |
| `Local` | Tests count dynamically (`len(SOURCE)`), and eval goldens and baselines have no hard counts, so adding data does not break them. |
| `Docs` | Wikipedia airport articles give IATA codes and coordinates (KIX, ITM). |
| `Docs` | Wikipedia landmark articles give attraction coordinates. |
| `Docs` | Wikimedia Commons gives hotel names and stable `upload.wikimedia.org` image URLs. |
| `Docs` | Wikipedia "Visa policy of <country>" gives the current rules for Vietnamese nationals, citing official sources. |
| `Docs` | The ECB euro reference rates (XML feed) give daily rates, for example 2026-09-25: 1 EUR = 179.70 JPY and 1 EUR = 1.1403 USD, so 1 USD ≈ 157.6 JPY. |
| `Docs` | Booking.com, Agoda, Tripadvisor and chain sites return 403 or time out, so live prices and star ratings cannot be scraped. |
| `Inference` | Haiku returned one impossible coordinate (`34°65′44″`). Web-sourced numbers need automatic sanity checks: a valid range, and within about 60 km of the city centre. |

## Local Findings

- **Relevant files:** `apps/api/app/data/{countries,cities,airports,airlines,hotels,places,tips,visa,fx}.py`, `content_translations.vi.json`, `app/db/seed.py`, `scripts/generate_translations.py`, `app/rag/ingest.py`.
- **Extension points:** append entries to the module lists and dicts. The import-time validators act as the integrity test.
- **Conventions to keep:**
  - UUID5 ids (check the namespace used by existing entries before generating new ones);
  - hotel codes of IATA prefix plus sequence;
  - `description` in the existing template style;
  - tips and airlines appended only;
  - 3 or more hotels and places per city.
- **Missing:** no id helper for new rows (compute UUID5 in a one-off script), no image-URL checker, and no translation-completeness check.

## Upstream Findings

- Wikivoyage "See / Sleep" sections are an alternative for places and hotel names, with a consistent structure per city.
- None of the upstream seed-data generators fit this repo's hand-curated module format. Build in-repo.

## Docs Findings

- **Official sources checked:** Wikipedia, Wikimedia Commons, the ECB FX feed, and national visa-policy pages.
- **Caveats:**
  - Official embassy and OTA pages often block automated fetches, so Wikipedia citations are the practical primary source.
  - Visa rules change, so record the check date.
  - FX is a single `LAST_UPDATED` for all rates. Updating it means refreshing every rate from the same ECB date, which keeps the whole table consistent.

## Recommendation

- **Primary:** extend the modules in place, in dependency order:
  1. countries, visa, fx (from ECB), and airlines (JAL/ANA, Korean Air, China Eastern, EVA, Air France, British Airways, TAP, ITA, Qantas, Emirates, Turkish, Delta/United, appended);
  2. airports;
  3. per region, cities, hotels (6–8 each), places (8 or more each) and tips;
  4. vi translations, via a script if a key is available, otherwise translated by a subagent into the same JSON shape.

  Web research runs on Haiku subagents, one per city batch. Each returns structured JSON with a source URL per record. An Opus/Sonnet assembler turns it into module entries, and a validation script checks coordinates, ranges and duplicates.
- **Why alternatives lost:**
  - A live OTA/places API contradicts the synthetic-inventory design and would add an external dependency.
  - Faking hotel names would undermine realism; names and images stay real.
- **What would change this:** if the user wants live prices, that is a provider integration, and a high-risk lane.

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:**
  - a `short_code` collision (verify by seeding);
  - web data errors from Haiku (mitigated by the sanity-check script and a spot-check review);
  - image URL rot (use Commons only);
  - a large diff to review (about 150 hotels and 200 places).
- **Evidence gaps:** star ratings and prices are indicative. Visa rules as of 2026-09 come from Wikipedia citations.
- **Follow-up questions:** none blocking.

## Source Pack

- **Local files read:** the data modules listed above, `app/db/seed.py`, `app/services/{flight,hotel}_service.py`, `app/rag/ingest.py`, `scripts/generate_translations.py`, `tests/repositories/test_reference_repos.py`, `eval/datasets/*.json`, `eval/baselines/main.json`.
- **Upstream repositories or pages checked:** Wikivoyage (Osaka), Wikimedia Commons hotel categories.
- **Official docs domains or pages checked:** en.wikipedia.org (Kansai International Airport, Itami Airport, Osaka Castle and other landmarks, Visa policy of Japan), commons.wikimedia.org, ecb.europa.eu (euro FX reference XML); booking.com, agoda.com and tripadvisor.com were blocked.

## Evidence Boundary

> Confirmed from artifacts: schemas and validators, region-agnostic flight/hotel generation, dynamic test counts, the RAG startup re-ingest, source reachability for one pilot city.
> Inferred from patterns: indicative pricing is acceptable because the existing data follows the same convention; the size of the `short_code` collision risk.
> Not checked: the 19 other cities' sources; translation-script cost/runtime.
