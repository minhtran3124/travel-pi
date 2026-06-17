<!--
  Canonical SUMMARY.md shape. Header block is machine-read by
  hooks/risk-corroboration.sh (Lane:) and the trust-metrics ledger.
-->

# places-nl-search — Summary

Lane: normal
Confidence: high
Reason: One flag fired — public-contract (new POST /places/search/nl endpoint). Read-only over existing place data, no schema/auth/external changes. No Step-3 hard gate, but the corroboration hook treats new public contracts as a gate (see public-contract-hard-gate memory) — authorize at commit, keep normal lane.
Flags: public-contract
Affects: places router/schema (new /search/nl contract), place_service (NL parse helper); reuses core/text.py fuzzy match
Input-type: spec slice

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane.

### Intent

> 10. ⬜ Natural-language search shim
>
> - `POST /places/search/nl` body `{query: "romantic dinner in Hanoi under $40"}` → parses to structured filters server-side (city/category/price_level/min_rating) and returns matches + the parsed filters back ("here's how I interpreted you"). Cheap to implement with keyword matching; the agent can also do the parsing itself, but having the server do it means a smaller/cheaper model can call the tool.

## What changed

Added `POST /places/search/nl` (`app/routers/places.py`): a free-text `{query}` is parsed
server-side by a pure keyword/regex parser (`place_service.parse_nl_query`) into
`{city, category, min_rating, price_level}`, which feeds the existing `search_places()` and
returns the paged matches plus the `parsed` filters echoed back ("here's how I interpreted
you"). No LLM, no new dependency — `re` + the existing canonical `CITIES` list. New schemas
`ParsedQuery` / `PlaceNLSearchRequest` / `PlaceNLSearchResponse` in `app/schemas/place.py`.
+24 tests (16 parser unit cases, 7 HTTP, +1 correctness-review regression test).

**Known scoped behavior:** `price_level` is matched **exactly** (band), not as a ≤ ceiling —
"under $40" → band 2 excludes band-1 places (Non-goal #3; documented in the schema docstring;
intent-review flagged report-only). Whitespace-only query is treated as no-signal (returns all,
paginated). City extraction is substring-based (documented v1 limitation).

### Rationale

Pure server-side keyword/fuzzy parsing (reuse `core/text.py` + existing place filters) over an
LLM call — the doc explicitly scopes it as "cheap to implement with keyword matching," and the
value is letting a smaller model offload parsing, not adding an inference dependency. Returns the
parsed filters alongside matches so the caller can see how the query was interpreted.

### Alternatives considered

- LLM-based parsing — rejected: out of scope per the doc ("keyword matching"), adds a model dependency this mock backend avoids.
- Reshape existing `GET /places/search` to accept free text — rejected: keeps the structured search contract intact; NL is an additive sibling endpoint.

### Deviations

- Rule 3 — Moved `import pytest` / `from app.services import place_service` to the top of `tests/test_places.py` (ruff E402/I001 on the spec's mid-file snippet). `tests/test_places.py`. Commit `fecb4b5`.
- Rule 1 — Widened `_NL_STAR_RE` from single-digit `(\d(?:\.\d)?)` to `(\d+(?:\.\d+)?)` so "10 star" is captured whole and clamped to 5.0 instead of mis-parsing to 0.0. Found by the final adversarial correctness review. `app/services/place_service.py`. Commit `bb2bd87`.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Full test suite | `.venv/bin/python -m pytest tests/ -q` | 0 | 559 passed (was 536 baseline; +23 new) |
| NL tests | `.venv/bin/python -m pytest tests/test_places.py -k "parse_nl_query or nl_search" -q` | 0 | 23 passed |
| Lint (changed files) | `ruff check app/schemas/place.py app/services/place_service.py app/routers/places.py tests/test_places.py` | 0 | All checks passed |
| Format (changed files) | `ruff format --check app/schemas/place.py app/services/place_service.py app/routers/places.py tests/test_places.py` | 0 | 4 files already formatted |

### Review gates

- Per-task: spec-compliance + code-quality (sonnet) ✅ on all 4 tasks.
- Final adversarial correctness review (sonnet, whole diff) — 1 MEDIUM bug fixed (`bb2bd87`); 2 findings accepted (whitespace no-signal, substring city) with rationale, no crash paths.
- Final intent review (sonnet, blind to PLAN) — faithfully satisfies the request; exact-match price_level flagged report-only (scoped Non-goal #3).

### Rollback

- `git revert bb2bd87 eece7d9 fecb4b5 ae5be3e` (or revert the branch merge). Purely additive — no migrations, no data changes.

### Harness-Delta

Public-contract boundary on a `normal`-lane task again — the known feature-intake ↔ hook
inconsistency (`public-contract-hard-gate` memory). Authorize at commit with
`RISK_WARN_CATEGORIES="public-contract"` and record in ESCALATIONS.md; not a new finding.
