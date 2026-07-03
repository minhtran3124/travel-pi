---
slug: min-48-dashboard-agent-config
status: proposed
owner: Minh Tran
created: 2026-07-02
issue: MIN-48
---

# MIN-48 — Dashboard to configure per-agent LLM settings

## 1. Motivation

Per-agent LLM config (provider / model / base_url / temperature / max_tokens) already
lives in the DB (`agent_config` table, MIN-43) and is loaded at runtime through an
in-process TTL cache (MIN-47). Today the only way to edit it is `scripts/seed_agent_config.py`.
MIN-48 adds a **server-rendered dashboard** — consistent with the existing `/dashboard/*`
pages — to view and edit that config through a UI, persisting changes to the DB and taking
effect at runtime without a restart.

## 2. Scope (resolved at intake, 2026-07-02)

Editable fields: **`provider`, `model`, `temperature`, `max_tokens`** (the five columns on
`AgentConfig`, minus `base_url` which is hidden — see §7). Owner decisions:

- **System prompt → deferred to MIN-45.** No prompt field, no YAML writer.
- **No auth** (project posture; dashboard `include_in_schema=False`). `last-updated-by` dropped.
- **Per-agent** editing — one row per agent in `AGENT_CONFIG_NODES`.
- **No Alembic migration** — `AgentConfig` inherits `UUIDBase`, so `created_at` / `updated_at`
  (with `onupdate`) already cover "last-updated-at".
- **tier / mode → out of scope** — `mode` was removed in MIN-43; `tier` is not a column.

## 3. Non-goals

System-prompt editing (MIN-45), prompt versioning, tier/mode, auth/authz, editing `base_url`,
adding agents outside `AGENT_CONFIG_NODES`, a JSON API surface.

## 4. Success criteria

- `GET /dashboard/agent-config` lists all 9 agents with their current DB config.
- `GET /dashboard/agent-config/{agent_name}` shows a pre-filled edit form; unknown agent → 404.
- `POST /dashboard/agent-config/{agent_name}` validates, persists via the service→repo path,
  invalidates the MIN-47 cache, and redirects back (PRG) with a success banner.
- Editing agent A never changes agent B's row.
- After a save, the running agent graph picks up the change (cache generation bumps → rebuild).

## 5. Architecture & data flow

Layering is strict `router → service → repository`; ORM stays in the repo (already built).

```
GET  /dashboard/agent-config
       → dashboard router
       → AgentConfigService.list_configs()
       → AgentConfigRepository.list_all()
       → render agent_config.html

GET  /dashboard/agent-config/{agent_name}
       → AgentConfigService.get_config(agent_name)   # 404 if not a known node
       → render agent_config_edit.html (prefilled)

POST /dashboard/agent-config/{agent_name}   (form-encoded)
       → AgentConfigService.update_config(agent_name, provider, model, temperature, max_tokens)
           → validate → AgentConfigRepository.upsert(...)  # base_url=None
           → AgentConfigCache.invalidate()
       → 303 redirect to GET edit page with ?saved=1   (Post/Redirect/Get)
```

### Reads come from the DB, not the cache

The list/edit pages read the DB (`repo.list_all` / `repo.get`) — the source of truth for what
will be edited. The MIN-47 cache is what the *running agent* uses; showing cache values could
display data up to ~1h stale in an editing UI. "Respect the cache" is honored by **invalidating
it on save** (below), not by reading through it.

## 6. Components

### 6.1 `AgentConfigService` — new (`app/services/agent_config_service.py`)

Sync service (no real I/O), constructed with the request-scoped `Session` like other dashboard
services (`HotelService(session)`).

- `list_configs() -> list[AgentConfigView]` — one entry per name in `AGENT_CONFIG_NODES`, merged
  with any DB row. A node with no row shows empty/"default" values (matches `get_agent_llm`
  per-field fallback to the global default).
- `get_config(agent_name) -> AgentConfigView` — raise `NotFoundError` if `agent_name` not in
  `AGENT_CONFIG_NODES`; return the DB row (or an empty view if unset).
- `update_config(agent_name, *, provider, model, temperature, max_tokens) -> None`:
  - Guard clauses first: `agent_name ∈ AGENT_CONFIG_NODES` (else `NotFoundError`); blank
    `provider` allowed (→ `None`), otherwise must be in `PROVIDER_NAMES` (else
    `DomainValidationError`); `temperature` parses to float and `max_tokens` to int when present
    (else `DomainValidationError`).
  - Normalize empty strings → `None` (per-field fallback to global default).
  - Always pass **`base_url=None`** (see §7).
  - `repo.upsert(agent_name, provider=…, model=…, base_url=None, temperature=…, max_tokens=…)`.
  - `AgentConfigCache.invalidate()`.

`AGENT_CONFIG_NODES` is imported from `app/data/agent_config.py` (existing single source of truth).

> **Layer note:** `app/data/*` is by convention imported only by `app/db/seed.py`. `AGENT_CONFIG_NODES`
> is a plain constant list of node names (no DB/seed coupling). If reusing it from the service is
> considered a convention breach during review, lift the list into `app/core/` (e.g.
> `core/agent_config_cache.py` or a small `core/agents.py`) and have both seed and service import it
> from there. Decide at plan time; either way there is a single source of truth.

### 6.2 Cache invalidation — small change to `app/core/agent_config_cache.py`

Add a classmethod:

```python
@classmethod
def invalidate(cls) -> None:
    """Force the next read to reload from the DB (called after a config write)."""
    cls._loaded_at = None
```

The next `AgentConfigCache.generation()` / `.get()` call triggers `_maybe_refresh` → reload from
DB → bump `generation` if the data changed → `graph.py` (`resolve_travel_graph`, generation check
at line ~173) rebuilds the compiled graph for the new generation on the next agent request. No synchronous reload inside the
dashboard request (keeps the write path light and avoids coupling the request-scoped session to
the isolated config session factory).

> **Rule-4 / high-blast:** `agent_config_cache.py` is a core file. The change is additive (a new
> method; no existing behavior altered). Rollback = `git revert <sha>`.

### 6.3 Routes — added to `app/routers/dashboard.py`

Three handlers on the existing `router` (prefix `/dashboard`, `include_in_schema=False`), using
the request-scoped `Depends(get_session)` like the other pages. The two writes to note:

- This is the **first mutating (POST) route** on the dashboard. Public-contract hard gate →
  authorize the commit with `RISK_WARN_CATEGORIES="public-contract"`.
- POST uses `RedirectResponse(status_code=303)` (PRG) so a browser refresh doesn't re-submit.

Form parsing: `provider: str = Form("")`, `model: str = Form("")`, `temperature: str = Form("")`,
`max_tokens: str = Form("")` (strings, so blank = "unset"; service coerces/validates). Requires
`python-multipart` for `Form(...)` support. It is present in the venv (v0.0.32) only
**transitively** via FastAPI and is **not pinned** in `apps/api/requirements.txt` — pin it
explicitly (Rule 3 auto-add, note in SUMMARY) so form parsing does not depend on a transitive dep.

### 6.4 Templates — new, extend `base.html`

- `agent_config.html` — table of the 9 agents: `agent · provider · model · temperature ·
  max_tokens · [Edit]`. Nodes with no row render a "default" badge.
- `agent_config_edit.html` — POST form:
  - `provider`: `<select>` with an empty "(global default)" option + the 5 `PROVIDER_NAMES`.
  - `model`: `<input list="models-…">` + `<datalist>` seeded from the selected provider's catalog
    models (reference hint) — **free text allowed** (catalog is reference, not an allowlist).
  - `temperature`, `max_tokens`: plain inputs.
  - Confirm-before-save via `onsubmit="return confirm(...)"`.
  - Shows `updated_at` (from `TimestampMixin`). Success banner when `?saved=1`.
- Add an "Agent config" link to `index.html` (dashboard home).

## 7. `base_url` handling

The edit form does **not** expose `base_url`; every save writes `base_url=None`. When the stored
override is `None`, `get_agent_llm` → `_build_chat_model` derives the endpoint from the chosen
provider profile's own `base_url` (`app/core/llm_providers.py`). Writing `None` (rather than
preserving a prior value) is deliberate: it keeps the endpoint correct after a provider change and
avoids a stale gateway URL. Any pre-existing per-agent `base_url` override is intentionally cleared
— the UI has no way to set one, and custom-gateway config is out of scope.

## 8. Error handling

Guard clauses first; use the existing exception factory (`app/exceptions.py`):

- Unknown `agent_name` → `NotFoundError` → 404.
- Invalid `provider` / unparseable `temperature`|`max_tokens` → `DomainValidationError`. Note
  `DomainValidationError.status_code` is **422** and `main.py` registers a generic `AppError`
  handler — so the POST handler MUST explicitly **catch `DomainValidationError`** and re-render the
  edit form (error message + submitted values preserved, no data loss) with `status_code=400`. If
  the exception is allowed to propagate instead, the generic handler returns 422 and there is no
  form re-render. Tests assert **400** + preserved inputs. (`repo.upsert` also rejects an unknown
  provider as a backstop.)

## 9. Testing

`tests/api/dashboard/test_agent_config_dashboard.py` (TestClient, SQLite):

| Check | Assert |
|---|---|
| GET list | 200; all 9 `AGENT_CONFIG_NODES` present |
| GET edit (known) | 200; prefilled from DB |
| GET edit (unknown agent) | 404 |
| POST happy | row persisted with expected fields; `base_url is None`; 303 → `?saved=1` |
| POST invalid provider | DB unchanged; 400; error shown; inputs preserved |
| Per-agent isolation | editing `planner` leaves `booking` row untouched |
| Cache invalidated | after POST, `AgentConfigCache.generation()` increases (data changed) |

Unit-test `AgentConfigService` with the request-scoped session fixture used by other dashboard
service tests. Keep coverage ≥80% on new files.

> **Test wiring caveat:** `_maybe_refresh` early-returns when `_session_factory is None`, so the
> cache-invalidation assertion is only meaningful when the cache is `configure()`d against the same
> test DB the POST wrote to. Run that test through the app lifespan (or `configure()` the cache in
> the fixture); a test that `clear()`s the cache and never configures it will not bump `generation`.

## 10. Risks

- **First dashboard write route** (public contract) — mitigated by PRG + validation; commit gate
  needs the `public-contract` category authorized.
- **Core cache file touched** — additive method only; rollback via `git revert`.
- **`base_url` clear-on-save** — intentional; documented in §7. Only affects rows that had a custom
  per-agent gateway (none in the default seed, which mirrors the provider profile).
- **`app/data` import convention** — resolved at plan time (§6.1): either import the constant or
  lift it to `core/`.

## 11. Status log

- 2026-07-02 — design drafted; intake forks resolved (defer system-prompt, no auth, per-agent, no
  migration); approach A (list → edit-per-agent) approved by owner.
