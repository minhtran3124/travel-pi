<!--
  Header block is machine-read by hooks/risk-corroboration.sh (Lane:) and the
  trust-metrics ledger.
-->

# place-category-meta — Summary

Lane: normal
Confidence: high
Reason: 2 flags (public-contract, existing-behavior). No data-model/migration (static metadata map, no table) — chosen approach deliberately avoids the migration hard gate. No other hard gate fires.
Flags: public-contract, existing-behavior
Affects: places public contract — `GET /places/categories` response_model changes `list[str]` → `list[PlaceCategoryInfo{name,color,icon}]`; touches `app/schemas/place.py`, `app/services/place_service.py`, `app/routers/places.py`, + a new static category-metadata map.
Input-type: spec slice
Route: normal — /using-git-worktrees (off `v2`) → /writing-plans → /subagent-driven-development (PLAN.md triggered: ~4 files > 2).
Escalate: no — the spec's static-vs-dynamic fork was resolved by the human at intake (see Rationale).

> `Lane` drives **ceremony**. `Confidence` drives **interruption**. The design fork that would
> have made this low-confidence was resolved interactively at intake, so it proceeds autonomously.

### Intent

> for A2. ⬜ Place categories có màu/icon (phân loại do người dùng định nghĩa)

A2 (verbatim from `specs/agent-platform-roadmap/CHECKLIST.md`):

> ### A2. ⬜ Place categories có màu/icon (phân loại do người dùng định nghĩa)
> - [ ] Bảng `categories` (name, color, icon) — hoặc enum mở rộng nếu muốn giữ tĩnh.
> - [ ] `place.category_id` (hiện đang là string `category`) — cân nhắc giữ string để không phá `PlaceCategory` enum hiện có; chỉ thêm `color`/`icon` metadata.
> - [ ] Endpoint `GET /places/categories` (đã có) → trả thêm color/icon.
> - *Phụ thuộc:* A1 (nếu gắn vào saved place). *Công sức:* Thấp-TB.

**Human decision at intake (resolving the spec's explicit fork):**
1. **Approach = static color/icon metadata** (not a dynamic user-defined table). Keep the string
   `category` and the `PlaceCategory` enum; add a static name→{color,icon} map; no table, no
   migration, no `category_id` FK.
2. **Surface scope = only `GET /places/categories`.** Place / SavedPlace responses are unchanged.

### Risk checklist (10 flags)

| # | Flag | Fires? | Why |
|---|---|---|---|
| 1 | Auth | no | — |
| 2 | Authorization | no | — |
| 3 | Data model | no | static map + response schema only; **no table / column / migration** (the deciding reason this is not high-risk) |
| 4 | Audit/security | no | — |
| 5 | External systems | no | — |
| 6 | Public contracts | **yes** | `GET /places/categories` element type changes `str` → object `{name,color,icon}` (FE codegen + clients of that endpoint affected) |
| 7 | Cross-platform | no | — |
| 8 | Existing behavior | **yes** | the existing `/categories` endpoint + its test change shape |
| 9 | Weak proof | no | places paths are well test-covered; plan adds a categories-shape test |
| 10 | Multi-domain | no | places only |

2 flags → **normal**.

### Hard-gate check

- **Data loss / migration:** NOT hit — the static-metadata approach was chosen specifically so no
  table/migration is introduced (the dynamic-table alternative would have tripped it).
- **Public contract:** per [[public-contract-hard-gate]] the feature-intake hard-gate list excludes
  "public-contract" (it is a normal flag here), and no corroboration hook is present in this repo.
  The shape change is intended and human-authorized at intake. If a hook is later added and flags it,
  authorize with `RISK_WARN_CATEGORIES="public-contract"` at commit.
- All other hard gates: not hit.

### Rationale

The spec forked between (A) static color/icon metadata keeping the string category, and (B) a
dynamic user-defined `categories` table + `place.category_id` FK + CRUD. Chose **A** because:
- The backend has **no auth/user layer** (CLAUDE.md), so "user-defined" categories (B) have no
  owner concept to attach to — B would add a table and a user notion the architecture lacks.
- The sub-bullets and effort estimate ("Thấp-TB", "chỉ thêm color/icon metadata", "giữ string để
  không phá `PlaceCategory` enum") already lean to A.
- `category` is already a free string derived from seed data (`place_service.CATEGORIES =
  sorted({p.category for p in _PLACES})`); A layers metadata on top without disturbing it.
- Color/icon values should align with the dashboard **DESIGN.md "Sunset"** system (per-card `--c`
  hues already used for tip categories + hotel types in `app/templates/base.html`) so the FE can
  reuse one palette — see [[[DESIGN.md]]] note in the plan.

### Alternatives considered

- **Dynamic `categories` table + `category_id` FK + CRUD** — rejected: introduces a migration and a
  user-ownership concept the mock backend has no layer for; over-built for "Thấp-TB".
- **Embed color/icon on every place/saved_place response** — rejected (surface scope): wider
  contract change than A2 asks for; clients can join against the categories list.

### Open assumptions (confidence high)

- Categories list stays **derived from seed data** (`place_service.CATEGORIES`); the metadata map
  must cover every value those seeds produce (a category with no metadata entry should fall back to
  a neutral color/icon, not error — plan to add a fallback + a test that every seed category has
  metadata).
- Color values are hex strings aligned with DESIGN.md tokens; icon values are short string keys the
  FE maps to its icon set (no binary/asset handling here).

### Verify (DONE — 2026-06-25)

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Categories endpoint shape | `.venv/bin/python -m pytest tests/ -k "categor" -q` | 0 | 35 passed; returns `[{name,color,icon}]`, sorted by name |
| Every seed category has metadata | `.venv/bin/python -m pytest tests/api/place/test_place_categories.py -q` | 0 | coverage + fallback tests pass |
| Full suite | `.venv/bin/python -m pytest tests/ -q` | 0 | 699 passed, no regressions |
| Lint | `ruff check app && ruff format --check <touched>` | 0 | touched files clean; 4 pre-existing unrelated format-drift files left untouched (surgical rule) |
