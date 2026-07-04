---
slug: agent-reflection-toggle
status: active
owner: Minh Tran
created: 2026-07-04
---

# Agent Reflection Toggle Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans (or subagent-driven-development) to implement this plan task-by-task.

**Goal:** Let the agent's **reflection** step be turned on/off through the DB-backed agent config, editable from the dashboard.

**Architecture:** The on/off behavior already flows through `AgentContext.allow_reflection` — the reflection node short-circuits to `END` when it is `False` (`app/agents/nodes.py:124`). This feature only adds a **DB source** for that flag: a nullable `enabled` column on `agent_config`, surfaced through the existing `AgentConfigCache` and read at request time in `resolve_agent_context`. `NULL`/absent = enabled (backward compatible); only an explicit `False` disables. A checkbox on the reflection edit page writes the flag; `AgentConfigCache.invalidate()` (already called on save) propagates it.

**Tech Stack:** FastAPI, SQLAlchemy ORM, Alembic (batch migration), Pydantic v2, Jinja2 dashboard templates, pytest (isolated temp SQLite per run), LangGraph.

**Design decisions (from `SUMMARY.md` / `ESCALATIONS.md`):**
- Storage → **Option A**: one nullable `enabled` boolean on `agent_config`; gate **reflection only**.
- Dashboard → add the checkbox now, on the reflection edit form only.
- Coalescing (`None → True`) happens on the **read side** (`_resolve_context`), so the cache/model stay raw and simple.

---

## 1. Motivation

Reflection adds an answer-quality loop but costs an extra LLM round-trip per turn. Operators need to toggle it without a code change or redeploy. The `allow_reflection` seam and its tests (`tests/agents/test_depth_toggles.py`) already exist; all that is missing is a DB-backed source for the flag and a UI to flip it.

## 2. Non-goals

- No generic per-agent enable/disable (only `reflection` is gated; the column is generic but nothing else reads it).
- No new toggle for `summarize` / `extract_memory` / sub-agents.
- No change to the reflection prompt, the `max_revisions` cap, or graph topology.
- No env/settings flag — the source of truth is the DB (`agent_config`).

## 3. Success Criteria

- `agent_config` has a nullable `enabled` column; `alembic upgrade head` applies clean on SQLite **and** Postgres.
- With `reflection.enabled = False` in the DB, a chat turn resolves `AgentContext.allow_reflection = False` and the reflection node goes straight to `END`.
- `NULL`/no row → reflection stays **on** (today's behavior); every existing test stays green.
- The dashboard reflection edit page shows an "Enabled" checkbox; unchecking + saving disables reflection and the change takes effect after cache invalidation.
- `ruff check` + `ruff format --check` clean; full `make test` green; `make test-docker` green.

## 4. Tasks

> **Migration note (read once):** per the `stale-travel-db-breaks-suite-on-schema-change` learning, after Task 1 rebuild the dev DB before running the wider suite: from `apps/api/` run `../../.venv/bin/alembic upgrade head` (and `make seed` if you use `travel.db` directly). The pytest suite builds an isolated temp SQLite DB per run, so it picks up the new column from the ORM automatically.

> **Signature-compat note:** every new argument below is a **keyword arg with a default** (`enabled: bool | None = None`, `allow_reflection: bool = True`). All current callers omit it and keep today's behavior — verified against `grep -rn resolve_agent_context` (only `agent.py:165` + tests, all keyword `tier=`) and `AgentModelOverride(` construction sites (none pass `enabled`).

### Task 1 — Add `enabled` column + migration

**Files:**
- Modify: `app/db/models/agent_config.py`
- Create: `alembic/versions/d2f4b6a8c0e1_add_agent_config_enabled.py`
- Test: `tests/db/test_agent_config_model.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/db/test_agent_config_model.py`:

```python
def test_agent_config_enabled_defaults_null_and_roundtrips(session):
    """`enabled` is nullable (NULL = on) and stores an explicit bool."""
    from app.db import models

    row = models.AgentConfig(agent_name="reflection")
    session.add(row)
    session.commit()
    session.refresh(row)
    assert row.enabled is None  # NULL default → treated as enabled downstream

    row.enabled = False
    session.commit()
    session.refresh(row)
    assert row.enabled is False
```

> Match the existing fixture style in this file — reuse its `session` fixture. If it uses a different fixture name (e.g. `db_session`), mirror that.

- [ ] **Step 2: Run test to verify it fails**

Run: `../../.venv/bin/python -m pytest tests/db/test_agent_config_model.py -x -q`
Expected: FAIL — `AgentConfig` has no attribute/column `enabled`.

- [ ] **Step 3: Add the column to the model**

In `app/db/models/agent_config.py`, add the `Boolean` import and the column after `max_tokens`:

```python
from sqlalchemy import Boolean, Float, Index, Integer, String
...
    max_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    # None == "enabled" (backward-compatible default); only an explicit False
    # disables the agent. Currently read only for the `reflection` node.
    enabled: Mapped[bool | None] = mapped_column(Boolean, default=None)
```

- [ ] **Step 4: Hand-author the Alembic migration**

Create `alembic/versions/d2f4b6a8c0e1_add_agent_config_enabled.py` (mirror `c7e9a2b5f4d1_add_agent_config_temperature_max_tokens.py`; `down_revision` MUST be the current head `c7e9a2b5f4d1`):

```python
"""add agent_config enabled

Revision ID: d2f4b6a8c0e1
Revises: c7e9a2b5f4d1
Create Date: 2026-07-04 22:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2f4b6a8c0e1"
down_revision: str | Sequence[str] | None = "c7e9a2b5f4d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("agent_config", schema=None) as batch_op:
        batch_op.add_column(sa.Column("enabled", sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("agent_config", schema=None) as batch_op:
        batch_op.drop_column("enabled")
```

> If `alembic heads` no longer returns `c7e9a2b5f4d1`, set `down_revision` to whatever `../../.venv/bin/alembic heads` prints — do not create a second head.

- [ ] **Step 5: Apply the migration + verify the test passes**

Run: `../../.venv/bin/alembic upgrade head && ../../.venv/bin/python -m pytest tests/db/test_agent_config_model.py -x -q`
Expected: migration applies clean; PASS.

```xml
<task id="1.1" wave="1">
  <files>app/db/models/agent_config.py, alembic/versions/d2f4b6a8c0e1_add_agent_config_enabled.py, tests/db/test_agent_config_model.py</files>
  <action>Add nullable Boolean `enabled` column to AgentConfig (None = on). Hand-author the additive Alembic migration with down_revision = current head. NULL-default keeps existing rows enabled.</action>
  <verify>cd apps/api && ../../.venv/bin/alembic upgrade head && ../../.venv/bin/python -m pytest tests/db/test_agent_config_model.py -x -q</verify>
  <done>Column exists, migration applies on SQLite, model test passes.</done>
</task>
```

### Task 2 — Carry `enabled` through the config cache

**Files:**
- Modify: `app/core/agent_config_cache.py`
- Test: `tests/core/test_agent_config_cache.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/core/test_agent_config_cache.py`:

```python
def test_override_carries_enabled_flag():
    """AgentModelOverride round-trips an explicit `enabled` bool; default is None."""
    from app.core.agent_config_cache import AgentConfigCache, AgentModelOverride

    assert AgentModelOverride().enabled is None  # unset → None (read side coalesces)
    AgentConfigCache.sync_from_cache(
        {"reflection": AgentModelOverride(enabled=False)}
    )
    assert AgentConfigCache.get("reflection").enabled is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../../.venv/bin/python -m pytest tests/core/test_agent_config_cache.py::test_override_carries_enabled_flag -x -q`
Expected: FAIL — `AgentModelOverride` has no field `enabled`.

- [ ] **Step 3: Add the field + map it on reload**

In `app/core/agent_config_cache.py`, add to the frozen dataclass and the DB mapping (keep it raw — no coalescing here):

```python
@dataclass(frozen=True)
class AgentModelOverride:
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    enabled: bool | None = None  # None = enabled (coalesced on the read side)
```

And in `reload_from_db`, add `enabled=row.enabled` to the `AgentModelOverride(...)` construction:

```python
        row.agent_name: AgentModelOverride(
            provider=row.provider,
            model=row.model,
            base_url=row.base_url,
            temperature=row.temperature,
            max_tokens=row.max_tokens,
            enabled=row.enabled,
        )
```

- [ ] **Step 4: Run tests to verify pass (incl. existing equality tests)**

Run: `../../.venv/bin/python -m pytest tests/core/test_agent_config_cache.py -x -q`
Expected: PASS — new test green; existing equality tests still green (default `enabled=None` on both sides).

```xml
<task id="2.1" wave="2">
  <files>app/core/agent_config_cache.py, tests/core/test_agent_config_cache.py</files>
  <action>Add `enabled: bool | None = None` to AgentModelOverride and map `enabled=row.enabled` in reload_from_db (references the Task 1.1 column, hence wave 2). No coalescing here — kept raw for the read side.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_agent_config_cache.py -x -q</verify>
  <done>Override carries enabled; existing cache tests unaffected.</done>
</task>
```

### Task 3 — Persist `enabled` through the repository

**Files:**
- Modify: `app/repositories/agent_config.py`
- Test: `tests/api/agent_config/test_agent_config_repo.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/api/agent_config/test_agent_config_repo.py` (match its existing repo/session fixture):

```python
def test_upsert_persists_enabled(session):
    from app.repositories.agent_config import AgentConfigRepository

    repo = AgentConfigRepository(lambda: session)  # match existing construction in this file
    repo.upsert("reflection", enabled=False)
    assert repo.get("reflection").enabled is False

    repo.upsert("reflection", enabled=True)
    assert repo.get("reflection").enabled is True
```

> Check how other tests in this file build `AgentConfigRepository` (it takes a session_factory via `Repo`); reuse that exact pattern rather than guessing.

- [ ] **Step 2: Run test to verify it fails**

Run: `../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_repo.py::test_upsert_persists_enabled -x -q`
Expected: FAIL — `upsert()` got an unexpected keyword argument `enabled`.

- [ ] **Step 3: Add the `enabled` param to `upsert`**

In `app/repositories/agent_config.py`, add the parameter and the assignment:

```python
    def upsert(
        self,
        agent_name: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        enabled: bool | None = None,
    ) -> "models.AgentConfig":
        ...
            row.temperature = temperature
            row.max_tokens = max_tokens
            row.enabled = enabled
            self._commit(s)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_repo.py -x -q`
Expected: PASS.

```xml
<task id="3.1" wave="2">
  <files>app/repositories/agent_config.py, tests/api/agent_config/test_agent_config_repo.py</files>
  <action>Add `enabled: bool | None = None` to AgentConfigRepository.upsert and assign `row.enabled = enabled`.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_repo.py -x -q</verify>
  <done>upsert persists enabled True/False; repo tests pass.</done>
</task>
```

### Task 4 — Read the flag at request time (context + router wiring)

**Files:**
- Modify: `app/agents/context.py`
- Modify: `app/routers/agent.py:143-165` (`_resolve_context`)
- Test: `tests/agents/test_agent_context.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/agents/test_agent_context.py`:

```python
def test_resolve_agent_context_honors_allow_reflection():
    """The new keyword flag threads into the resolved context; default stays True."""
    from app.agents.context import resolve_agent_context

    assert resolve_agent_context(tier="free").allow_reflection is True
    assert (
        resolve_agent_context(tier="free", allow_reflection=False).allow_reflection
        is False
    )
```

Add to `tests/agents/test_agent_context.py` (router coalescing — anonymous path needs no DB session):

```python
def test_resolve_context_disables_reflection_from_db_config():
    """`_resolve_context` reads reflection.enabled from the cache (None → on)."""
    from app.core.agent_config_cache import AgentConfigCache, AgentModelOverride
    from app.routers import agent as agent_router

    AgentConfigCache.clear()
    AgentConfigCache.sync_from_cache({"reflection": AgentModelOverride(enabled=False)})
    try:
        ctx = agent_router._resolve_context("anon", False, session=None)
        assert ctx.allow_reflection is False
    finally:
        AgentConfigCache.clear()
```

> `_resolve_context` only touches `session` when `authenticated=True`; the anonymous branch (`authenticated=False`) returns `Tier.FREE` without a DB read, so passing `session=None` is safe. Confirm this against `app/routers/agent.py:159-165` before relying on it.

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/bin/python -m pytest tests/agents/test_agent_context.py -x -q`
Expected: FAIL — `resolve_agent_context()` got an unexpected keyword `allow_reflection` (and the router still hardcodes True).

- [ ] **Step 3: Add the `allow_reflection` param to `resolve_agent_context`**

In `app/agents/context.py`, change the signature and the returned context (leave the docstring's "single policy function" intent intact; context.py must NOT import the cache — the flag is passed in from the boundary):

```python
def resolve_agent_context(
    *, tier: Tier | str | None, allow_reflection: bool = True
) -> AgentContext:
    ...
    return AgentContext(
        tier=tier,
        allow_reflection=allow_reflection,
        allow_memory_write=True,
        allow_episodic=True,
        response_style=ResponseStyle.DEFAULT,
        allowed_subagents=allowed_subagents,
        max_revisions=1,
    )
```

Add a one-line docstring note: `:param allow_reflection: DB-config-driven reflection gate (from agent_config.enabled); defaults True.`

- [ ] **Step 4: Wire the cache read into `_resolve_context`**

In `app/routers/agent.py`, add the import (top of file, with the other `app.core` imports):

```python
from app.core.agent_config_cache import AgentConfigCache
```

Then in `_resolve_context`, coalesce `None → True` and thread the flag through:

```python
    if authenticated:
        user_repo = UserRepository(session)
        user_repo.ensure_user(effective_user_id)
        tier = user_repo.get_tier(effective_user_id)
    else:
        tier = Tier.FREE.value
    refl = AgentConfigCache.get("reflection")
    allow_reflection = True if (refl is None or refl.enabled is None) else refl.enabled
    return resolve_agent_context(tier=tier, allow_reflection=allow_reflection)
```

- [ ] **Step 5: Run tests to verify pass**

Run: `../../.venv/bin/python -m pytest tests/agents/test_agent_context.py tests/agents/test_depth_toggles.py tests/agents/test_tier_gating.py -x -q`
Expected: PASS — new tests green; tier-gating + depth-toggle tests unaffected.

```xml
<task id="4.1" wave="3">
  <files>app/agents/context.py, app/routers/agent.py, tests/agents/test_agent_context.py</files>
  <action>Add `allow_reflection: bool = True` param to resolve_agent_context. In `_resolve_context`, read AgentConfigCache.get("reflection"), coalesce None→True, and pass it through. Keep context.py free of cache imports (read at the router boundary).</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_agent_context.py tests/agents/test_depth_toggles.py -x -q</verify>
  <done>DB reflection.enabled=False → allow_reflection False; NULL/absent → True; existing context tests pass.</done>
</task>
```

### Task 5 — Surface `enabled` through the service

**Files:**
- Modify: `app/services/agent_config_service.py`
- Test: `tests/api/agent_config/test_agent_config_service.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/api/agent_config/test_agent_config_service.py` (match its existing service/session fixture):

```python
def test_update_config_persists_enabled_and_view_reflects_it(session):
    from app.services.agent_config_service import AgentConfigService

    svc = AgentConfigService(session)
    svc.update_config(
        "reflection", provider="", model="", temperature="", max_tokens="",
        enabled=False,
    )
    assert svc.get_config("reflection").enabled is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_service.py::test_update_config_persists_enabled_and_view_reflects_it -x -q`
Expected: FAIL — `update_config()` got an unexpected keyword `enabled` (and `AgentConfigView` has no `enabled`).

- [ ] **Step 3: Add `enabled` to the view, mapping, and update path**

In `app/services/agent_config_service.py`:

Add to `AgentConfigView`:

```python
@dataclass(frozen=True)
class AgentConfigView:
    agent_name: str
    description: str | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    updated_at: str | None = None
    enabled: bool | None = None
```

Map it in `_to_view` (both branches):

```python
    @staticmethod
    def _to_view(row, agent_name: str) -> AgentConfigView:
        description = AGENT_DESCRIPTIONS.get(agent_name)
        if row is None:
            return AgentConfigView(agent_name=agent_name, description=description)
        return AgentConfigView(
            agent_name=agent_name,
            description=description,
            provider=row.provider,
            model=row.model,
            temperature=row.temperature,
            max_tokens=row.max_tokens,
            updated_at=row.updated_at,
            enabled=row.enabled,
        )
```

Add the param to `update_config` and pass it to `upsert` (default `True` — only the reflection form sends a real value; every other save writes `True`, i.e. "on", which is a no-op for gating):

```python
    def update_config(
        self,
        agent_name: str,
        *,
        provider: str,
        model: str,
        temperature: str,
        max_tokens: str,
        enabled: bool = True,
    ) -> None:
        ...
        self._repo.upsert(
            agent_name,
            provider=prov,
            model=_norm(model),
            base_url=None,
            temperature=temp,
            max_tokens=maxt,
            enabled=enabled,
        )
        AgentConfigCache.invalidate()
```

- [ ] **Step 4: Run tests to verify pass**

Run: `../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_service.py -x -q`
Expected: PASS.

```xml
<task id="5.1" wave="3">
  <files>app/services/agent_config_service.py, tests/api/agent_config/test_agent_config_service.py</files>
  <action>Add `enabled` to AgentConfigView + _to_view mapping; add `enabled: bool = True` to update_config and forward to repo.upsert. Cache invalidation already present.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_service.py -x -q</verify>
  <done>Service persists + returns enabled; existing service tests pass.</done>
</task>
```

### Task 6 — Dashboard checkbox (route + template)

**Files:**
- Modify: `app/routers/dashboard.py:876-978` (`_render_agent_config_edit`, `agent_config_edit_page`, `agent_config_save`)
- Modify: `app/templates/agent_config_edit.html`
- Test: `tests/api/agent_config/test_agent_config_dashboard.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/api/agent_config/test_agent_config_dashboard.py` (match its existing `client` fixture):

```python
def test_reflection_edit_page_shows_enabled_checkbox(client):
    resp = client.get("/dashboard/agent-config/reflection")
    assert resp.status_code == 200
    assert 'name="enabled"' in resp.text
    assert 'name="enabled_marker"' in resp.text


def test_saving_reflection_unchecked_disables_it(client):
    # Unchecked checkbox submits no `enabled`; the hidden marker signals intent.
    resp = client.post(
        "/dashboard/agent-config/reflection",
        data={"provider": "", "model": "", "temperature": "", "max_tokens": "",
              "enabled_marker": "1"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    from app.services.agent_config_service import AgentConfigService
    # Reuse the app's session dependency the same way other tests in this file do
    # to assert persisted state, OR re-GET the edit page and assert the checkbox
    # is no longer `checked`.
    reget = client.get("/dashboard/agent-config/reflection")
    assert "checked" not in reget.text.split('name="enabled"')[1].split(">")[0]


def test_non_reflection_edit_page_has_no_checkbox(client):
    resp = client.get("/dashboard/agent-config/supervisor")
    assert resp.status_code == 200
    assert 'name="enabled_marker"' not in resp.text
```

> If asserting persisted state directly is simpler than string-slicing the re-GET, use whatever DB-inspection helper the other dashboard tests already use. Keep one positive (disabled) and one negative (no checkbox on non-reflection) assertion.

- [ ] **Step 2: Run tests to verify they fail**

Run: `../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_dashboard.py -x -q`
Expected: FAIL — no `enabled` field rendered; route ignores the checkbox.

- [ ] **Step 3: Thread `enabled` through the render helper + routes**

In `app/routers/dashboard.py`:

`_render_agent_config_edit` — add a param and pass it into the template context:

```python
def _render_agent_config_edit(
    request: Request,
    *,
    agent_name: str,
    provider: str,
    model: str,
    temperature: str,
    max_tokens: str,
    enabled: bool | None = None,
    updated_at: str | None = None,
    error: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return _TEMPLATES.TemplateResponse(
        request=request,
        name="agent_config_edit.html",
        context={
            "agent_name": agent_name,
            "provider_value": provider,
            "model_value": model,
            "temperature_value": temperature,
            "max_tokens_value": max_tokens,
            "enabled_value": enabled,
            "updated_at": updated_at,
            "error": error,
            "providers": sorted(PROVIDER_NAMES),
            "model_hints": _model_hints(),
        },
        status_code=status_code,
    )
```

`agent_config_edit_page` — pass the view's flag:

```python
    return _render_agent_config_edit(
        request,
        agent_name=v.agent_name,
        provider=v.provider or "",
        model=v.model or "",
        temperature="" if v.temperature is None else str(v.temperature),
        max_tokens="" if v.max_tokens is None else str(v.max_tokens),
        enabled=v.enabled,
        updated_at=v.updated_at,
    )
```

`agent_config_save` — accept the checkbox + marker, compute the bool, forward it, and echo it back on the validation-error re-render:

```python
def agent_config_save(
    request: Request,
    agent_name: str,
    session: Annotated[Session, Depends(get_session)],
    provider: str = Form(""),
    model: str = Form(""),
    temperature: str = Form(""),
    max_tokens: str = Form(""),
    enabled: str | None = Form(None),
    enabled_marker: str | None = Form(None),
) -> Response:
    svc = AgentConfigService(session)
    svc.get_config(agent_name)  # 404 before any write if the agent is unknown
    # Unchecked checkboxes submit nothing; the hidden marker says "this form owns
    # the flag". No marker (non-reflection forms) → default enabled (True/on).
    enabled_val = True if enabled_marker is None else (enabled == "on")
    try:
        svc.update_config(
            agent_name,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            enabled=enabled_val,
        )
    except DomainValidationError as exc:
        return _render_agent_config_edit(
            request,
            agent_name=agent_name,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            enabled=enabled_val,
            error=str(exc),
            status_code=400,
        )
    return RedirectResponse(url="/dashboard/agent-config?saved=1", status_code=303)
```

- [ ] **Step 4: Add the checkbox to the template (reflection only)**

In `app/templates/agent_config_edit.html`, insert before the `<button type="submit">Save</button>` line:

```html
  {% if agent_name == 'reflection' %}
  <label>
    <input type="hidden" name="enabled_marker" value="1">
    <input type="checkbox" name="enabled" value="on"
           {% if enabled_value is not false %}checked{% endif %}>
    Reflection enabled
  </label>
  {% endif %}
```

> `enabled_value` is `None` (no row / NULL) or `True` → `is not false` renders `checked`; only an explicit `False` renders unchecked. Matches the read-side `None → on` coalescing.

- [ ] **Step 5: Run tests to verify pass**

Run: `../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_dashboard.py -x -q`
Expected: PASS.

```xml
<task id="6.1" wave="4">
  <files>app/routers/dashboard.py, app/templates/agent_config_edit.html, tests/api/agent_config/test_agent_config_dashboard.py</files>
  <action>Render an "Enabled" checkbox + hidden `enabled_marker` on the reflection edit form only. In agent_config_save compute enabled from (marker, checkbox) and forward to the service; echo it back on validation error. No marker → default on.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_dashboard.py -x -q</verify>
  <done>Reflection page shows the checkbox; unchecking + save disables reflection; other agents show no checkbox; PRG redirect intact.</done>
</task>
```

### Task 7 — Full-suite + lint + Docker parity gate

**Files:** none (verification only).

- [ ] **Step 1: Lint + format**

Run: `ruff check app scripts && ruff format --check app scripts`
Expected: clean. (Fix with `ruff format app scripts` if needed.)

- [ ] **Step 2: Rebuild dev DB, then full SQLite suite**

Run: `../../.venv/bin/alembic upgrade head && make test`
Expected: all green (watch `tests/db/test_seed_agent_config.py` + `tests/api/agent_config/*` — a new nullable column must not break row-shape assertions; if one hard-codes a column count, update it and note it under Deviations).

- [ ] **Step 3: Docker Postgres parity**

Run: `make test-docker`
Expected: green — confirms the Boolean `add_column` migration applies on Postgres too (per `docker-py312-vs-local-py314`, Docker runs Python 3.12; watch for order/annotation drift).

- [ ] **Step 4: Manual smoke (optional, dashboard)**

`make dev`, open `/dashboard/agent-config/reflection`, uncheck "Reflection enabled", Save. Re-open — checkbox stays unchecked. A subsequent chat turn (after cache invalidation) skips reflection (`[agent] reflection → END (no revision)` in logs, or no reflection log at all since the node still runs but short-circuits).

```xml
<task id="7.1" wave="5">
  <files>none</files>
  <action>Run lint, full SQLite suite (after alembic upgrade head), and Docker Postgres parity. Optionally smoke the dashboard toggle end-to-end. This is a phase-level acceptance gate, so `make test` may exceed the 60s task-verify guideline by design.</action>
  <verify>cd apps/api && ruff check app scripts && ../../.venv/bin/alembic upgrade head && make test</verify>
  <done>Lint clean; make test + make test-docker green.</done>
</task>
```

## 5. Risks

- **Checkbox-not-submitted ambiguity** — unchecked HTML checkboxes send nothing. Mitigated by the hidden `enabled_marker` field: no marker ⇒ "form doesn't own the flag" ⇒ default on. Verified by `test_saving_reflection_unchecked_disables_it` + `test_non_reflection_edit_page_has_no_checkbox`.
- **Existing row-shape assertions** — a new nullable column can trip a test that counts columns or compares full rows (`test_seed_agent_config.py`, model tests). Task 7 Step 2 surfaces it; fix + record under Deviations.
- **Stale `travel.db`** — the dev DB won't gain the column via `create_all`; run `alembic upgrade head` (Task 1 Step 5 + Task 7 Step 2), per `stale-travel-db-breaks-suite-on-schema-change`.
- **Cache propagation delay** — a toggle only takes effect after `AgentConfigCache.invalidate()` (already called in `update_config`) → next read reloads. No graph rebuild needed (the flag is per-request context, not a baked model). Acceptable.
- **`ruff-on-edit` stripping imports** — add the `Boolean` import (Task 1) and `AgentConfigCache` import (Task 4) together with their first use in the same edit, per `ruff-on-edit-strips-unused-imports`.

## 6. Status Log

- 2026-07-04 — Plan drafted from `/feature-intake` findings (design fork resolved: Option A, reflection-only, dashboard checkbox now). Ready for review + execution.
- 2026-07-04 — Executed via subagent-driven-development (each task: TDD + spec review + quality review, all ✅/Approved):
  - Wave 1 — Task 1.1 `436d5e5` (enabled column + migration)
  - Wave 2 — Task 2.1 `b0f1069` (cache field), Task 3.1 `bf2eeb0` (repo upsert)
  - Wave 3 — Task 4.1 `dcc82f3` (context param + router wiring), Task 5.1 `2211ed9` (service)
  - Wave 4 — Task 6.1 `c52b4bc` (dashboard checkbox + template)
  - Wave 5 — Task 7.1: gates PASSED. Lint clean; `pytest -q` 1258 passed (6 pre-existing env failures, confirmed on baseline `3cf7603`); `make test-docker` exit 0.
  - Post-task correctness review (`/correctness-review`, opus, whole diff) found a P1 + 2×P3 (unconditional `enabled` write let modal/CLI/non-reflection saves clobber the toggle). Fixed in `1c6faed` (preserve-on-absent + toggle moved into the real modal UI). Re-review ✅ 0 bugs.
  - Intent review (`/intent-review`, sonnet, blind to PLAN) ✅ no divergence.
  - Also fixed a coupled test spy in `83031c4` (Task 4 signature change).
  - Status: implementation complete + all gates green. Awaiting user go-ahead for push + PR (`finishing-a-development-branch`).
