---
slug: places-nl-search
status: active
owner: Minh Tran
created: 2026-06-17
---

# Natural-Language Place Search Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Add `POST /places/search/nl` that turns a free-text query (e.g. "romantic dinner in Hanoi under $40") into structured filters server-side, runs the existing place search, and echoes back how the query was interpreted.

**Architecture:** A pure keyword/regex parser in `place_service` maps the query to `{city, category, min_rating, price_level}` (no LLM, no new dependency), reusing the canonical city list and the existing `search_places()` filter pipeline. The router orchestrates parse → search → paginate, mirroring the existing `GET /places/search` handler. Parsed filters are returned alongside results so the caller sees the interpretation.

**Tech Stack:** FastAPI, Pydantic v2, Python `re` + stdlib only. Tests via `fastapi.testclient.TestClient` (existing `client` fixture in `tests/conftest.py`).

---

## 1. Motivation

AGENT_IMPROVEMENTS.md #10: let a smaller/cheaper model offload query parsing to the server. The agent sends one sentence; the server returns matches **and** the structured filters it extracted ("here's how I interpreted you").

## 2. Non-goals

- No LLM-based parsing — keyword/regex only (doc scopes it as "cheap to implement with keyword matching").
- No change to the existing `GET /places/search` contract — NL is an additive sibling endpoint.
- No range semantics for price — a budget ("under $40") maps to a **single** `price_level` band, matched exactly, consistent with `search_places()`'s existing exact-match behavior. This simplification is documented in the response schema and echoed back via `parsed.price_level`.

## 3. Success Criteria

- `POST /places/search/nl` with `{"query": "romantic dinner in Hanoi under $40"}` returns 200 with `parsed.city == "Hanoi"`, `parsed.category == "restaurant"`, `parsed.price_level == 2`, and every result matching those filters.
- Empty/missing `query` → 422.
- Unrecognised words are ignored (no error); a query with no extractable filters returns all places (paginated), with all `parsed` fields `null`.
- `ruff check` / `ruff format --check` clean; full suite green.

## 4. Tasks

### Task 1 — Response & request schemas

**Files:**
- Modify: `app/schemas/place.py` (append after `PlaceSearchResponse`, end of file ~line 123)

- [ ] **Step 1: Add the three models**

Append to `app/schemas/place.py`:

```python
class ParsedQuery(AppBaseModel):
    """How the server interpreted a natural-language places query."""

    city: str | None = Field(
        default=None,
        description="City resolved from the query (canonical name), or null.",
        examples=["Hanoi"],
    )
    category: str | None = Field(
        default=None,
        description="Place category inferred from keywords, or null.",
        examples=["restaurant"],
    )
    min_rating: float | None = Field(
        default=None,
        description="Minimum rating inferred (e.g. '4 star', 'best'), or null.",
        examples=[4.5],
    )
    price_level: int | None = Field(
        default=None,
        description=(
            "Price band 1–4 inferred from a budget ('under $40') or adjective "
            "('cheap'). Matched exactly (not a ceiling). Null if none found."
        ),
        examples=[2],
    )


class PlaceNLSearchRequest(AppBaseModel):
    """Request body for ``POST /places/search/nl``."""

    query: str = Field(
        min_length=1,
        description="Free-text request to interpret.",
        examples=["romantic dinner in Hanoi under $40"],
    )


class PlaceNLSearchResponse(PagedResponse[Place]):
    """Response body for ``POST /places/search/nl``."""

    query: str = Field(description="The original query, echoed back.")
    parsed: ParsedQuery = Field(
        description="Structured filters the server extracted from the query."
    )
```

- [ ] **Step 2: Verify it imports and constructs**

Run: `.venv/bin/python -c "from app.schemas.place import ParsedQuery, PlaceNLSearchRequest, PlaceNLSearchResponse; PlaceNLSearchResponse(total=0, limit=20, offset=0, results=[], query='x', parsed=ParsedQuery())"`
Expected: exit 0, no output.

**Done:** the three models import and `PlaceNLSearchResponse` instantiates.

---

### Task 2 — NL parser in `place_service`

**Files:**
- Modify: `app/services/place_service.py` (add `import re` at top; append parser block after `search_places`, ~line 88)
- Test: `tests/test_places.py` (append unit tests)

- [ ] **Step 1: Write the failing unit tests**

Append to `tests/test_places.py`:

```python
# ── NL query parsing (service-level) ──────────────────────────────────────────

import pytest

from app.services import place_service


@pytest.mark.parametrize(
    "query, field, expected",
    [
        ("romantic dinner in Hanoi under $40", "city", "Hanoi"),
        ("romantic dinner in Hanoi under $40", "category", "restaurant"),
        ("romantic dinner in Hanoi under $40", "price_level", 2),
        ("cheap coffee in Da Nang", "category", "cafe"),
        ("cheap coffee in Da Nang", "price_level", 1),
        ("cheap coffee in Da Nang", "city", "Da Nang"),
        ("best museums to visit", "category", "attraction"),
        ("best museums to visit", "min_rating", 4.5),
        ("4 star hotels", "min_rating", 4.0),
        ("luxury shopping", "price_level", 4),
        ("luxury shopping", "category", "shopping"),
        ("nothing useful here", "city", None),
        ("nothing useful here", "category", None),
        ("nothing useful here", "price_level", None),
        ("nothing useful here", "min_rating", None),
    ],
)
def test_parse_nl_query(query, field, expected) -> None:
    parsed = place_service.parse_nl_query(query)
    assert getattr(parsed, field) == expected
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_places.py -k parse_nl_query -v`
Expected: FAIL — `AttributeError: module 'app.services.place_service' has no attribute 'parse_nl_query'`.

- [ ] **Step 3: Implement the parser**

Add `import re` near the top of `app/services/place_service.py` (with the other imports), import `ParsedQuery` from the place schema, and append after `search_places`:

```python
# --- Natural-language query parsing (POST /places/search/nl) ------------------
# Pure keyword/regex extraction — no LLM. The caller gets the parsed filters
# echoed back so a small model can see how its query was interpreted.

# Category inferred from keywords; checked in order, first hit wins.
_NL_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("restaurant", ("restaurant", "dinner", "lunch", "breakfast", "brunch",
                     "dining", "dine", "eat", "food", "meal")),
    ("cafe", ("cafe", "café", "coffee", "espresso", "tea")),
    ("nightlife", ("nightlife", "bar", "club", "pub", "drinks", "cocktail")),
    ("shopping", ("shopping", "shop", "mall", "market", "store", "boutique")),
    ("activity", ("activity", "tour", "adventure", "experience", "workshop", "class")),
    ("attraction", ("attraction", "sight", "sightseeing", "museum", "temple",
                     "landmark", "gallery", "park", "visit")),
]

# Price band inferred from adjective keywords; checked in order.
_NL_PRICE_KEYWORDS: list[tuple[int, tuple[str, ...]]] = [
    (1, ("cheap", "budget", "free", "affordable", "inexpensive")),
    (2, ("moderate", "mid-range", "midrange", "reasonable")),
    (3, ("expensive", "pricey", "upscale")),
    (4, ("luxury", "luxurious", "fancy", "high-end", "fine dining")),
]

# "under $40", "$40", "under 40" → capture the dollar amount.
_NL_BUDGET_RE = re.compile(r"\$\s*(\d+(?:\.\d+)?)|under\s+(\d+(?:\.\d+)?)")
# "4 star", "4.5 stars", "4+ star" → capture the rating.
_NL_STAR_RE = re.compile(r"(\d(?:\.\d)?)\s*\+?\s*stars?")
_NL_TOP_RATED = ("highly rated", "top-rated", "top rated", "highest rated", "best")


def _budget_to_price_level(amount: float) -> int:
    """Map a max-dollar budget to a single price band (1–4)."""
    if amount <= 20:
        return 1
    if amount <= 50:
        return 2
    if amount <= 100:
        return 3
    return 4


def _nl_has_word(query: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", query) is not None


def _nl_city(query: str) -> str | None:
    """Longest canonical city name appearing in the query (case-insensitive)."""
    hits = [c for c in CITIES if c.lower() in query]
    return max(hits, key=len) if hits else None


def _nl_category(query: str) -> str | None:
    for category, words in _NL_CATEGORY_KEYWORDS:
        if any(_nl_has_word(query, w) for w in words):
            return category
    return None


def _nl_price_level(query: str) -> int | None:
    budget = _NL_BUDGET_RE.search(query)
    if budget:
        return _budget_to_price_level(float(budget.group(1) or budget.group(2)))
    for level, words in _NL_PRICE_KEYWORDS:
        if any(_nl_has_word(query, w) for w in words):
            return level
    return None


def _nl_min_rating(query: str) -> float | None:
    star = _NL_STAR_RE.search(query)
    if star:
        return max(0.0, min(5.0, float(star.group(1))))
    if any(phrase in query for phrase in _NL_TOP_RATED):
        return 4.5
    return None


def parse_nl_query(query: str) -> "ParsedQuery":
    """Parse a free-text places query into structured filters.

    Pure keyword/regex extraction over the lowercased query. Unrecognised
    words are ignored; any field with no signal comes back ``None``. The
    returned city is the canonical name (e.g. "Hanoi"), so it feeds straight
    into :func:`search_places`.
    """
    q = query.lower()
    return ParsedQuery(
        city=_nl_city(q),
        category=_nl_category(q),
        min_rating=_nl_min_rating(q),
        price_level=_nl_price_level(q),
    )
```

Add the import alongside the existing schema import at the top:

```python
from app.schemas.place import NearbyPlace, ParsedQuery, Place
```

> Note: since `ParsedQuery` is imported at the top of the file, use an unquoted annotation — `def parse_nl_query(query: str) -> ParsedQuery:` (the `"ParsedQuery"` form shown above is only needed if you skip the import).

- [ ] **Step 4: Run to verify the unit tests pass**

Run: `.venv/bin/python -m pytest tests/test_places.py -k parse_nl_query -v`
Expected: PASS (all parametrized cases).

**Done:** `parse_nl_query` returns a `ParsedQuery` with the documented extractions; the 15 parametrized cases pass.

---

### Task 3 — `POST /places/search/nl` route + HTTP tests

**Files:**
- Modify: `app/routers/places.py` (extend the place schema import ~line 12-17; add the route after `search_places`, ~line 134)
- Test: `tests/test_places.py` (append HTTP integration tests)

- [ ] **Step 1: Write the failing HTTP tests**

Append to `tests/test_places.py`:

```python
# ── NL search endpoint (HTTP) ─────────────────────────────────────────────────

def test_nl_search_status(client: TestClient) -> None:
    resp = client.post("/places/search/nl", json={"query": "dinner in Hanoi"})
    assert resp.status_code == 200


def test_nl_search_echoes_parsed_filters(client: TestClient) -> None:
    body = client.post(
        "/places/search/nl",
        json={"query": "romantic dinner in Hanoi under $40"},
    ).json()
    assert body["query"] == "romantic dinner in Hanoi under $40"
    assert body["parsed"] == {
        "city": "Hanoi",
        "category": "restaurant",
        "min_rating": None,
        "price_level": 2,
    }


def test_nl_search_results_match_parsed_filters(client: TestClient) -> None:
    body = client.post(
        "/places/search/nl",
        json={"query": "romantic dinner in Hanoi under $40"},
    ).json()
    assert body["total"] >= 1
    for place in body["results"]:
        assert place["city"] == "Hanoi"
        assert place["category"] == "restaurant"
        assert place["price_level"] == 2


def test_nl_search_empty_query_422(client: TestClient) -> None:
    assert client.post("/places/search/nl", json={"query": ""}).status_code == 422


def test_nl_search_missing_query_422(client: TestClient) -> None:
    assert client.post("/places/search/nl", json={}).status_code == 422


def test_nl_search_no_signal_returns_all_with_null_parsed(client: TestClient) -> None:
    body = client.post("/places/search/nl", json={"query": "show me stuff"}).json()
    assert body["parsed"] == {
        "city": None,
        "category": None,
        "min_rating": None,
        "price_level": None,
    }
    assert body["total"] > 0


def test_nl_search_pagination(client: TestClient) -> None:
    body = client.post(
        "/places/search/nl?limit=2",
        json={"query": "show me stuff"},
    ).json()
    assert body["limit"] == 2
    assert len(body["results"]) <= 2
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_places.py -k nl_search -v`
Expected: FAIL — 404 (route not registered) on the status/echo tests.

- [ ] **Step 3: Add the route**

Extend the place schema import in `app/routers/places.py`:

```python
from app.schemas.place import (
    Place,
    PlaceListResponse,
    PlaceNearbyResponse,
    PlaceNLSearchRequest,
    PlaceNLSearchResponse,
    PlaceSearchResponse,
)
```

Add this route immediately after the `search_places` function (after line ~133, before `/cities`):

```python
@router.post(
    "/search/nl",
    response_model=PlaceNLSearchResponse,
    summary="Natural-language place search",
    responses=error_responses(422),
)
def search_places_nl(
    body: PlaceNLSearchRequest,
    pagination: PaginationDep,
) -> PlaceNLSearchResponse:
    """Parse a free-text query into structured filters, then search.

    The parsed filters are echoed back in ``parsed`` so the caller can see
    how the query was interpreted. Budget phrases ('under $40') and price
    adjectives ('cheap') map to a single ``price_level`` band, matched
    exactly; unrecognised words are ignored. Pagination uses the standard
    ``limit`` / ``offset`` query params.
    """
    parsed = place_service.parse_nl_query(body.query)
    all_results = place_service.search_places(
        city=parsed.city,
        category=parsed.category,
        min_rating=parsed.min_rating,
        price_level=parsed.price_level,
    )
    page, total = pagination.page_of(all_results)
    return PlaceNLSearchResponse(
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
        query=body.query,
        parsed=parsed,
        results=page,
    )
```

- [ ] **Step 4: Run to verify the HTTP tests pass**

Run: `.venv/bin/python -m pytest tests/test_places.py -k nl_search -v`
Expected: PASS (all 7 cases).

**Done:** endpoint returns matches + echoed `parsed` filters; 422 on empty/missing query; pagination works.

---

### Task 4 — Full suite + lint gate

**Files:** none (verification only)

- [ ] **Step 1: Run the whole suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass (336 existing + new NL tests), no regressions.

- [ ] **Step 2: Lint + format check**

Run: `ruff check app && ruff format --check app`
Expected: exit 0, "All checks passed".

**Done:** green suite + clean ruff.

---

## 5. Risks

- **Exact-match price band:** "under $40" → band 2 excludes price-level-1 places that are also under $40. Deliberate (keeps `search_places` exact-match semantics); the interpretation is surfaced via `parsed.price_level` so it's not silent. Revisit only if range filtering is requested.
- **City extraction is substring-based:** matches canonical names as they appear ("in Hanoi", "in Da Nang"). A heavily mistyped city ("hanwoi") won't resolve — acceptable for v1; the agent can fall back to `GET /places/search?city=`.
- **Public-contract gate:** new endpoint trips `risk-corroboration.sh`. Authorized as additive (see `ESCALATIONS.md`); commit with `RISK_WARN_CATEGORIES="public-contract"`.

## 6. Status Log

- 2026-06-17 — Plan drafted (status: proposed). Normal lane, confidence high (see SUMMARY.md).
- 2026-06-17 — Executed via subagent-driven-development on `feat/places-nl-search`. All 4 tasks green, per-task spec+quality reviews ✅.
  - Task 1 (schemas) — `ae5be3e`
  - Task 2 (parser + 16 unit tests) — `fecb4b5`
  - Task 3 (route + 7 HTTP tests) — `eece7d9`
  - Correctness-review fix (multi-digit star rating) — `bb2bd87`
  - Final correctness ✅ (1 bug fixed) + intent ✅ (report-only: exact-match price_level). 559 tests pass.

## 7. Wave / execution notes

Tasks are sequential (schema → service → router → suite); each depends on the prior, so no parallel waves. File touches: Task 1 → `schemas/place.py`; Task 2 → `services/place_service.py` + `tests/test_places.py`; Task 3 → `routers/places.py` + `tests/test_places.py`; Task 4 → none. Tasks 2 and 3 both append to `tests/test_places.py` but run in sequence, so no overlap conflict.
