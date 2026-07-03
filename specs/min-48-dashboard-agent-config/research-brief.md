# Research Brief — MIN-48 Agent-config dashboard

**Depth:** Deep (new dependency pin `python-multipart`; first mutating dashboard route = shared
public contract; touches agent runtime-config path). Most discovery was completed and
code-verified during brainstorming; this brief records the reuse map and the two non-obvious
integration risks (test wiring for cache invalidation; `app/data` import convention).

> ⚠️ **xia2 PROJECT.md is stale (harness-delta).** `.claude/skills/xia2/PROJECT.md` is the generic
> *harness-skills* template (high-blast = `hooks/*.sh` / `settings.json`; states "no DB session
> layer"). It does **not** describe this FastAPI backend, so its automated Deep/Quick signal
> mappings were not used. Findings below come from **verified local reads**, not guessed mappings.
> Recommend running `/bootstrap-xia2` to regenerate PROJECT.md for `apps/api/` before the next
> xia2 run. Matches memory `specs-tracked-not-gitignored` (xia2 template drift is known here).

## 1. What this repo is (verified)

- **Stack:** FastAPI backend at `apps/api/` (`fastapi>=0.110,<0.137`, `jinja2>=3.1,<4`), SQLAlchemy
  ORM, SQLite local / Postgres docker, Alembic migrations. `Local` — `apps/api/requirements.txt`.
- **Dashboard = server-rendered Jinja2**, separate from the JSON API, mounted at `/dashboard`
  (`include_in_schema=False`). `Local` — `app/routers/dashboard.py`.

## 2. What already exists (reuse map) — the lightest path is almost all reuse

| Need | Reuse (exists) | Evidence |
|---|---|---|
| Config model | `AgentConfig` (agent_name unique + provider/model/base_url/temperature/max_tokens) | `Local` `app/db/models/agent_config.py` |
| Data access | `AgentConfigRepository.list_all / get / upsert` (upsert validates provider vs `PROVIDER_NAMES`) | `Local` `app/repositories/agent_config.py` |
| Runtime cache | `AgentConfigCache` (TTL refresh, `generation`, `_loaded_at`); `reload_from_db` | `Local` `app/core/agent_config_cache.py` |
| Provider catalog | `PROVIDER_NAMES` (5 profiles), per-provider model reference lists | `Local` `app/core/llm_providers.py` |
| Agent node list | `AGENT_CONFIG_NODES` (9 nodes) | `Local` `app/data/agent_config.py` |
| Graph rebuild | `resolve_travel_graph` rebuilds when `AgentConfigCache.generation()` changes | `Local` `app/agents/graph.py:151-180` |
| base_url derivation | `get_agent_llm` → `_build_chat_model`: `base_url or profile.base_url or s.llm_base_url` | `Local` `app/clients/llm.py:118-150, ~81` |
| Timestamps | `AgentConfig(UUIDBase)` → `TimestampMixin.updated_at` (`onupdate`) — covers "last-updated-at", no migration | `Local` `app/db/base.py` |

**To build (new):** `AgentConfigService` (service layer — none exists for agent config yet),
3 routes on the dashboard router, 2 Jinja templates, `AgentConfigCache.invalidate()` (1 additive
method), tests. Everything else is reuse.

## 3. Convention findings (how to add routes/services/templates here)

- **Dashboard service pattern:** services are **constructed directly with the request session** in
  the handler — `HotelService(session)` where `session: Annotated[Session, Depends(get_session)]`.
  No module-level singletons (post di-session refactor). → `AgentConfigService(session)`.
  `Local` `app/routers/dashboard.py:325`, `app/services/hotel_service.py`.
- **Routes:** add to the existing `router` in `dashboard.py` (prefix `/dashboard`,
  `include_in_schema=False`). All current routes are **GET**; MIN-48 adds the **first POST** and the
  **first `Form(...)`** in the app (grep: no existing `Form(` usage). → `python-multipart` becomes a
  real (not just transitive) requirement.
- **Templates:** `{% extends "base.html" %}`, tokens in `base.html` `:root`; GET filter forms use
  `<form method="get">` + `<select onchange="this.form.submit()">`. `Local` `app/templates/hotels.html`.
- **Exceptions:** raise domain exceptions, never `HTTPException`. `DomainValidationError.status_code
  = 422`; `NotFoundError → 404`; generic `AppError` handler registered in `main.py`. **Implication:**
  to return **400 + re-rendered form** on invalid input (design §8), the POST handler must **catch
  `DomainValidationError`** and render — letting it propagate yields 422 with no form. `Local`
  `app/exceptions.py`, `app/main.py`.

## 4. Two non-obvious integration risks (the real value of this brief)

### 4.1 Cache-invalidation test cannot assert through HTTP under the current fixture

The `client` fixture (`tests/conftest.py:33-65`) overrides **only** `get_session` (the request
dependency) and runs the app lifespan via `with TestClient(app) as c:`. But lifespan wires the cache
loader to `settings.database_url`:

```
_config_factory = get_session_factory(settings.database_url)   # lifespan.py:50
AgentConfigCache.configure(_config_factory, ttl)               # NOT the test temp DB
```

So a POST through the client writes to the **temp DB** (override), while `AgentConfigCache` reloads
from the **settings DB**. An HTTP-level "generation bumps after POST" assertion is therefore
unreliable/wrong. `Local` `tests/conftest.py`, `app/core/lifespan.py:50-52`.

**Lightest credible test (recommend):** verify invalidation at the **service/cache level**, not
through HTTP —
- Primary: `AgentConfigService.update_config(...)` calls `AgentConfigCache.invalidate()`; assert
  `AgentConfigCache._loaded_at is None` afterward (decoupled from any DB factory). Existing cache
  tests already drive the class directly — `Local` `tests/core/test_agent_config_cache.py`.
- Thorough (optional): `configure()` the cache against the **same temp DB factory**, upsert, call
  `invalidate()`, then assert `generation()` increments after the lazy reload.
- HTTP tests cover persistence + status codes + isolation; leave generation to the unit test.

### 4.2 `app/data` import convention

`AGENT_CONFIG_NODES` lives in `app/data/agent_config.py`. CLAUDE.md convention: `from app.data`
appears **only** in `app/db/seed.py`. Importing it from `AgentConfigService` would be the first
exception. **Options (decide at plan time):** (a) import it anyway (it's a plain constant, no seed
coupling) and note the deviation, or (b) lift the list to `app/core/` (e.g. beside the cache) and
have both seed and service import from there — single source of truth, no convention breach.
`Local` CLAUDE.md, `app/data/agent_config.py`.

## 5. Dependency change

`python-multipart` is present only **transitively** (v0.0.32 via FastAPI) and **not pinned** in
`apps/api/requirements.txt`. FastAPI's own docs require it for `Form(...)`. → pin it explicitly
(Rule-3 auto-add; record in SUMMARY). `Docs` FastAPI "Request Forms" (needs `python-multipart`);
`Local` `apps/api/requirements.txt` (no multipart line).

## 6. Test placement

`tests/api/agent_config/` already exists (repo tests). Put the new dashboard tests either there or a
new `tests/api/dashboard/`; use the shared `client` fixture (HTTP) and `seeded_session` (service
units). `Local` `tests/api/agent_config/`, `tests/conftest.py:76-83`.

## 7. Upstream / Docs

Low value here — the feature is internal-pattern reuse (add-a-dashboard-page), not a new
integration. Only external touch point: FastAPI form handling requires `python-multipart` (§5),
which is a documented, version-independent requirement. No upstream library adoption needed.

## 8. Recommended path (reuse > adapt > build)

1. **Reuse** `AgentConfigRepository`, `AgentConfigCache`, `PROVIDER_NAMES`, `AGENT_CONFIG_NODES`,
   dashboard router + `base.html`, `client`/`seeded_session` fixtures.
2. **Build minimal:** `AgentConfigService` (validate + upsert + `invalidate`), 3 routes, 2 templates,
   `AgentConfigCache.invalidate()`.
3. **Watch:** the 400-vs-422 catch (§3), the cache-test wiring (§4.1), the `app/data` import (§4.2),
   pin `python-multipart` (§5), write `base_url=None` on save (design §7).

No design changes required — the spec already reflects these. Ready for `/writing-plans`.
