---
slug: min-48-dashboard-agent-config
status: active
owner: Minh Tran
created: 2026-07-02
---

# Agent-config Dashboard (MIN-48) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Add a server-rendered `/dashboard/agent-config` UI to view and edit per-agent LLM config
(provider / model / temperature / max_tokens), persisted to the DB and applied to the running agent
graph without a restart.

**Architecture:** `router (dashboard.py) → AgentConfigService → AgentConfigRepository` (reuse
MIN-43). Saves call `AgentConfigCache.invalidate()` so the MIN-47 cache reloads and the graph
rebuilds on its next read. Reads come from the DB (source of truth for editing), not the cache.
First mutating route on the dashboard; PRG + `Form(...)`.

**Tech Stack:** FastAPI, Jinja2, SQLAlchemy (existing), `python-multipart` (newly pinned).

**Lane:** high-risk (public-contract new write endpoint). Commits touching the new route need
`RISK_WARN_CATEGORIES="public-contract"` (see `specs/min-48-dashboard-agent-config/SUMMARY.md`).

**Plan-time decisions (locked):**
- **`AGENT_CONFIG_NODES` import:** import directly from `app.data.agent_config` in the service. It
  is a plain constant (no seed coupling); lifting it to `core/` is more blast for no benefit. This
  is the first `from app.data` outside `app/db/seed.py` — record the deviation in SUMMARY.
- **`base_url`:** never exposed; every save writes `base_url=None` (client derives it from the
  provider profile — design §7).
- **Invalid input:** the POST handler **catches `DomainValidationError`** (native 422) and
  re-renders the form with `status_code=400` + preserved inputs (design §8).
- **Cache-invalidation test:** asserted at the service/cache level, NOT through HTTP — the `client`
  fixture only overrides `get_session`, while the cache loader binds `settings.database_url`
  (research-brief §4.1).

---

## File structure

| File | Action | Responsibility |
|---|---|---|
| `apps/api/requirements.txt` | modify | Pin `python-multipart` (Form support) |
| `apps/api/app/core/agent_config_cache.py` | modify | Add additive `invalidate()` classmethod |
| `apps/api/app/services/agent_config_service.py` | create | Validate + upsert (`base_url=None`) + cache invalidate; DB→view mapping |
| `apps/api/app/routers/dashboard.py` | modify | 3 routes: GET list, GET edit, POST save (PRG + 400-on-invalid) |
| `apps/api/app/templates/agent_config.html` | create | Table of 9 agents + Edit links |
| `apps/api/app/templates/agent_config_edit.html` | create | Edit form (provider select, model datalist, temp, max_tokens) |
| `apps/api/app/templates/index.html` | modify | Link to the new page from the dashboard home |
| `apps/api/tests/core/test_agent_config_cache.py` | modify | Test `invalidate()` |
| `apps/api/tests/api/agent_config/test_agent_config_service.py` | create | Service unit tests (validation, base_url=None, isolation, cache) |
| `apps/api/tests/api/agent_config/test_agent_config_dashboard.py` | create | HTTP tests (list, edit, POST persist/redirect, 400, 404) |

All commands below run from `apps/api/`. Test runner: `../../.venv/bin/python -m pytest`.

---

## Chunk 1: Config-dashboard vertical slice

### Task 1.1 — Pin python-multipart

```xml
<task id="1.1" wave="1">
  <files>apps/api/requirements.txt</files>
  <action>FastAPI Form(...) support requires python-multipart, currently present only transitively. Add an explicit pin near the fastapi line: `python-multipart>=0.0.7,<0.1`. Match the existing comment/formatting style of the file.</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "import multipart; print(multipart.__version__)"</verify>
  <done>python-multipart is pinned in requirements.txt and importable.</done>
</task>
```

- [ ] **Step 1:** Add `python-multipart>=0.0.7,<0.1` to `apps/api/requirements.txt` beside the `fastapi` pin.
- [ ] **Step 2:** Verify import: `cd apps/api && ../../.venv/bin/python -c "import multipart; print(multipart.__version__)"` → prints a version.

---

### Task 1.2 — `AgentConfigCache.invalidate()`

**Files:**
- Modify: `apps/api/app/core/agent_config_cache.py`
- Test: `apps/api/tests/core/test_agent_config_cache.py`

- [ ] **Step 1: Write the failing test** (append to the existing test file)

```python
def test_invalidate_forces_next_read_to_reload():
    from app.core.agent_config_cache import AgentConfigCache, AgentModelOverride

    AgentConfigCache.clear()
    AgentConfigCache.sync_from_cache({"planner": AgentModelOverride(model="gpt-4o")})
    assert AgentConfigCache._loaded_at is not None  # "loaded" state

    AgentConfigCache.invalidate()

    assert AgentConfigCache._loaded_at is None  # next read will reload
```

- [ ] **Step 2: Run it, expect FAIL**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_agent_config_cache.py::test_invalidate_forces_next_read_to_reload -xvs`
Expected: FAIL — `AttributeError: ... has no attribute 'invalidate'`.

- [ ] **Step 3: Implement** — add to `class AgentConfigCache` (near `clear`)

```python
    @classmethod
    def invalidate(cls) -> None:
        """Force the next read to reload from the DB (called after a config write).

        Resets only the freshness stamp; the cached map stays in place until the
        next ``_maybe_refresh`` actually reloads. A no-op when no loader is wired.
        """
        cls._loaded_at = None
```

- [ ] **Step 4: Run it, expect PASS**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_agent_config_cache.py -x`
Expected: PASS (whole file green).

```xml
<task id="1.2" wave="1">
  <files>apps/api/app/core/agent_config_cache.py, apps/api/tests/core/test_agent_config_cache.py</files>
  <action>Add an additive `AgentConfigCache.invalidate()` classmethod that sets `_loaded_at = None` so the next `_maybe_refresh` reloads from the DB. TDD per steps above. Do not alter existing cache behavior. High-blast core file — additive only; rollback via git revert.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/core/test_agent_config_cache.py -x</verify>
  <done>invalidate() resets _loaded_at; existing cache tests stay green.</done>
</task>
```

---

### Task 2.1 — `AgentConfigService`

**Files:**
- Create: `apps/api/app/services/agent_config_service.py`
- Test: `apps/api/tests/api/agent_config/test_agent_config_service.py`

- [ ] **Step 1: Write failing tests**

```python
import pytest
from app.core.agent_config_cache import AgentConfigCache
from app.data.agent_config import AGENT_CONFIG_NODES
from app.exceptions import DomainValidationError, NotFoundError
from app.services.agent_config_service import AgentConfigService


def test_list_configs_returns_every_node(seeded_session):
    svc = AgentConfigService(seeded_session)
    configs = svc.list_configs()
    assert {c.agent_name for c in configs} == set(AGENT_CONFIG_NODES)
    assert len(configs) == len(AGENT_CONFIG_NODES)


def test_get_config_unknown_agent_raises_not_found(seeded_session):
    svc = AgentConfigService(seeded_session)
    with pytest.raises(NotFoundError):
        svc.get_config("does-not-exist")


def test_update_persists_and_forces_base_url_none(seeded_session):
    svc = AgentConfigService(seeded_session)
    svc.update_config("planner", provider="openai", model="gpt-4o",
                      temperature="0.5", max_tokens="1024")
    v = svc.get_config("planner")
    assert (v.provider, v.model, v.temperature, v.max_tokens) == ("openai", "gpt-4o", 0.5, 1024)
    # base_url is always cleared (hidden field, derived from provider)
    assert svc._repo.get("planner").base_url is None


def test_update_blank_fields_become_none(seeded_session):
    svc = AgentConfigService(seeded_session)
    svc.update_config("planner", provider="", model="", temperature="", max_tokens="")
    v = svc.get_config("planner")
    assert (v.provider, v.model, v.temperature, v.max_tokens) == (None, None, None, None)


def test_update_invalid_provider_raises(seeded_session):
    svc = AgentConfigService(seeded_session)
    with pytest.raises(DomainValidationError):
        svc.update_config("planner", provider="bogus", model="x",
                          temperature="", max_tokens="")


def test_update_invalid_temperature_raises(seeded_session):
    svc = AgentConfigService(seeded_session)
    with pytest.raises(DomainValidationError):
        svc.update_config("planner", provider="", model="",
                          temperature="hot", max_tokens="")


def test_update_is_per_agent_isolated(seeded_session):
    svc = AgentConfigService(seeded_session)
    svc.update_config("booking", provider="anthropic", model="claude-sonnet-5",
                      temperature="", max_tokens="")
    svc.update_config("planner", provider="openai", model="gpt-4o-mini",
                      temperature="", max_tokens="")
    b = svc.get_config("booking")
    assert (b.provider, b.model) == ("anthropic", "claude-sonnet-5")


def test_update_invalidates_cache(seeded_session):
    AgentConfigCache.clear()
    AgentConfigCache.sync_from_cache({})          # sets _loaded_at
    assert AgentConfigCache._loaded_at is not None
    AgentConfigService(seeded_session).update_config(
        "planner", provider="openai", model="gpt-4o", temperature="", max_tokens="")
    assert AgentConfigCache._loaded_at is None     # invalidate() ran
```

- [ ] **Step 2: Run, expect FAIL** — `ModuleNotFoundError: app.services.agent_config_service`.

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_service.py -x`

- [ ] **Step 3: Implement the service**

```python
"""AgentConfigService — validate + persist per-agent LLM config, invalidate cache."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.agent_config_cache import AgentConfigCache
from app.core.llm_providers import PROVIDER_NAMES
from app.data.agent_config import AGENT_CONFIG_NODES  # first app.data import outside seed.py — see PLAN decision
from app.exceptions import DomainValidationError, NotFoundError
from app.repositories.agent_config import AgentConfigRepository


@dataclass(frozen=True)
class AgentConfigView:
    """Read view for one agent's config (no ORM leak past the service)."""

    agent_name: str
    provider: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    updated_at: str | None = None


def _norm(value: str | None) -> str | None:
    """Empty/whitespace → None; otherwise the stripped string."""
    if value is None:
        return None
    v = value.strip()
    return v or None


def _parse_number(field: str, value: str | None, caster):
    """Parse a numeric form field; blank → None; bad input → DomainValidationError."""
    v = _norm(value)
    if v is None:
        return None
    try:
        return caster(v)
    except ValueError as exc:
        raise DomainValidationError(f"Invalid {field}: {value!r}") from exc


class AgentConfigService:
    """Per-agent LLM config: list/get/update over AgentConfigRepository."""

    def __init__(self, session: Session) -> None:
        self._repo = AgentConfigRepository(session)

    def list_configs(self) -> list[AgentConfigView]:
        """Return one view per node in AGENT_CONFIG_NODES, merged with DB rows."""
        rows = {r.agent_name: r for r in self._repo.list_all()}
        return [self._to_view(rows.get(name), name) for name in AGENT_CONFIG_NODES]

    def get_config(self, agent_name: str) -> AgentConfigView:
        """Return the view for *agent_name*; NotFoundError if not a known node."""
        self._require_known(agent_name)
        return self._to_view(self._repo.get(agent_name), agent_name)

    def update_config(self, agent_name: str, *, provider: str, model: str,
                      temperature: str, max_tokens: str) -> None:
        """Validate + persist config for *agent_name*, then invalidate the cache."""
        self._require_known(agent_name)
        prov = _norm(provider)
        if prov is not None and prov not in PROVIDER_NAMES:
            raise DomainValidationError(f"Unknown provider: {prov!r}")
        temp = _parse_number("temperature", temperature, float)
        maxt = _parse_number("max_tokens", max_tokens, int)
        self._repo.upsert(
            agent_name,
            provider=prov,
            model=_norm(model),
            base_url=None,  # hidden field — client derives it from the provider profile
            temperature=temp,
            max_tokens=maxt,
        )
        AgentConfigCache.invalidate()

    def _require_known(self, agent_name: str) -> None:
        if agent_name not in AGENT_CONFIG_NODES:
            raise NotFoundError(f"Unknown agent: {agent_name!r}")

    @staticmethod
    def _to_view(row, agent_name: str) -> AgentConfigView:
        if row is None:
            return AgentConfigView(agent_name=agent_name)
        return AgentConfigView(
            agent_name=agent_name,
            provider=row.provider,
            model=row.model,
            temperature=row.temperature,
            max_tokens=row.max_tokens,
            updated_at=row.updated_at,
        )
```

- [ ] **Step 4: Run, expect PASS**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_service.py -x`
Expected: PASS (all 7 tests).

```xml
<task id="2.1" wave="2">
  <files>apps/api/app/services/agent_config_service.py, apps/api/tests/api/agent_config/test_agent_config_service.py</files>
  <action>Create AgentConfigService (list/get/update) as coded above: validate provider vs PROVIDER_NAMES, parse temperature/max_tokens (blank→None, bad→DomainValidationError), always upsert base_url=None, call AgentConfigCache.invalidate() after write, map ORM→AgentConfigView. Import AGENT_CONFIG_NODES from app.data.agent_config (record deviation in SUMMARY). TDD per steps.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_service.py -x</verify>
  <done>All 7 service tests pass; base_url written as None; cache invalidated on update.</done>
</task>
```

---

### Task 3.1 — Templates + dashboard-home link

**Files:**
- Create: `apps/api/app/templates/agent_config.html`
- Create: `apps/api/app/templates/agent_config_edit.html`
- Modify: `apps/api/app/templates/index.html`

No unit test (rendered by the HTTP tests in Task 4.1). Templates extend `base.html` and use its
existing `{% block title %}` / `{% block content %}` blocks (mirror `hotels.html`).

- [ ] **Step 1: Create `agent_config.html`**

```html
{% extends "base.html" %}
{% block title %}Agent Config{% endblock %}
{% block content %}
<h1>Agent LLM configuration</h1>
{% if request.query_params.get('saved') %}
  <div class="banner banner-success">Configuration saved.</div>
{% endif %}
<table class="data-table">
  <thead>
    <tr><th>Agent</th><th>Provider</th><th>Model</th><th>Temp</th><th>Max tokens</th><th></th></tr>
  </thead>
  <tbody>
    {% for c in configs %}
    <tr>
      <td>{{ c.agent_name }}</td>
      <td>{{ c.provider or "—" }}</td>
      <td>{{ c.model or "—" }}</td>
      <td>{{ c.temperature if c.temperature is not none else "—" }}</td>
      <td>{{ c.max_tokens if c.max_tokens is not none else "—" }}</td>
      <td><a href="/dashboard/agent-config/{{ c.agent_name }}">Edit</a></td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endblock %}
```

- [ ] **Step 2: Create `agent_config_edit.html`**

```html
{% extends "base.html" %}
{% block title %}Edit · {{ agent_name }}{% endblock %}
{% block content %}
<h1>Edit config · {{ agent_name }}</h1>
{% if error %}<div class="banner banner-error">{{ error }}</div>{% endif %}
<form method="post" action="/dashboard/agent-config/{{ agent_name }}"
      onsubmit="return confirm('Save config for {{ agent_name }}? This changes the live agent model.');">
  <label>Provider
    <select name="provider">
      <option value="" {% if not provider_value %}selected{% endif %}>(global default)</option>
      {% for p in providers %}
      <option value="{{ p }}" {% if provider_value == p %}selected{% endif %}>{{ p }}</option>
      {% endfor %}
    </select>
  </label>
  <label>Model
    <input type="text" name="model" value="{{ model_value }}" list="model-hints"
           placeholder="(global default)">
    <datalist id="model-hints">
      {% for m in model_hints %}<option value="{{ m }}">{% endfor %}
    </datalist>
  </label>
  <label>Temperature
    <input type="text" name="temperature" value="{{ temperature_value }}" placeholder="(default)">
  </label>
  <label>Max tokens
    <input type="text" name="max_tokens" value="{{ max_tokens_value }}" placeholder="(default)">
  </label>
  <button type="submit">Save</button>
  <a href="/dashboard/agent-config">Cancel</a>
</form>
{% if updated_at %}<p class="muted">Last updated: {{ updated_at }}</p>{% endif %}
{% endblock %}
```

- [ ] **Step 3: Modify `index.html`** — add a link to `/dashboard/agent-config` alongside the
  existing dashboard-page links/cards. Match the sibling markup already in the file; example anchor:

```html
<a href="/dashboard/agent-config">Agent config</a>
```

- [ ] **Step 4: Sanity-check templates load** (Jinja parse, no server)

Run:
```
cd apps/api && ../../.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; e=Environment(loader=FileSystemLoader('app/templates')); [e.get_template(t) for t in ('agent_config.html','agent_config_edit.html','index.html')]; print('ok')"
```
Expected: prints `ok` (templates parse; extends/blocks resolve).

```xml
<task id="3.1" wave="3">
  <files>apps/api/app/templates/agent_config.html, apps/api/app/templates/agent_config_edit.html, apps/api/app/templates/index.html</files>
  <action>Create the two templates as coded above (list table + edit form with provider select, model datalist, temp/max_tokens inputs, confirm-before-save, saved/error banners, updated_at). Add a link to /dashboard/agent-config on the dashboard home (index.html), matching sibling markup. Reuse base.html blocks and existing CSS classes; if a referenced class is absent, fall back to the closest existing dashboard class.</action>
  <verify>cd apps/api && ../../.venv/bin/python -c "from jinja2 import Environment, FileSystemLoader; e=Environment(loader=FileSystemLoader('app/templates')); [e.get_template(t) for t in ('agent_config.html','agent_config_edit.html','index.html')]; print('ok')"</verify>
  <done>Both templates + index.html parse under Jinja; edit form posts to the correct action.</done>
</task>
```

---

### Task 4.1 — Dashboard routes + HTTP tests

**Files:**
- Modify: `apps/api/app/routers/dashboard.py`
- Test: `apps/api/tests/api/agent_config/test_agent_config_dashboard.py`

- [ ] **Step 1: Write failing HTTP tests**

```python
from app.data.agent_config import AGENT_CONFIG_NODES


def test_list_page_shows_all_agents(client):
    r = client.get("/dashboard/agent-config")
    assert r.status_code == 200
    for name in AGENT_CONFIG_NODES:
        assert name in r.text


def test_edit_page_renders_for_known_agent(client):
    r = client.get("/dashboard/agent-config/planner")
    assert r.status_code == 200
    assert "planner" in r.text


def test_edit_page_unknown_agent_404(client):
    r = client.get("/dashboard/agent-config/nope")
    assert r.status_code == 404


def test_post_persists_and_redirects(client):
    r = client.post(
        "/dashboard/agent-config/planner",
        data={"provider": "openai", "model": "gpt-4o", "temperature": "0.3", "max_tokens": ""},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "saved=1" in r.headers["location"]
    # persisted: the follow-up GET shows the new model
    assert "gpt-4o" in client.get("/dashboard/agent-config/planner").text


def test_post_invalid_provider_returns_400_and_preserves_input(client):
    r = client.post(
        "/dashboard/agent-config/planner",
        data={"provider": "bogus", "model": "keep-me", "temperature": "", "max_tokens": ""},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert "keep-me" in r.text        # user input preserved
    assert "bogus" in r.text or "provider" in r.text.lower()


def test_post_unknown_agent_404(client):
    r = client.post(
        "/dashboard/agent-config/nope",
        data={"provider": "", "model": "", "temperature": "", "max_tokens": ""},
        follow_redirects=False,
    )
    assert r.status_code == 404
```

- [ ] **Step 2: Run, expect FAIL** — routes not defined (404 on list, etc.).

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_dashboard.py -x`

- [ ] **Step 3: Implement the routes** in `app/routers/dashboard.py`

Add imports (top of file, with existing imports). `dashboard.py` has **no**
`from __future__ import annotations`, so the `-> Response` return annotation is evaluated at
def-time — `Response` MUST be imported or the module fails at import:

```python
from fastapi import Form, Response
from fastapi.responses import RedirectResponse

from app.core.llm_providers import LLM_PROVIDERS, PROVIDER_NAMES
from app.exceptions import DomainValidationError
from app.services.agent_config_service import AgentConfigService
```

Add a small render helper + the three routes (anywhere among the other route defs):

```python
def _model_hints() -> list[str]:
    """Union of catalog models across providers — datalist hints, not an allowlist."""
    return sorted({m for p in LLM_PROVIDERS.values() for m in p.models})


def _render_agent_config_edit(
    request: Request,
    *,
    agent_name: str,
    provider: str,
    model: str,
    temperature: str,
    max_tokens: str,
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
            "updated_at": updated_at,
            "error": error,
            "providers": sorted(PROVIDER_NAMES),
            "model_hints": _model_hints(),
        },
        status_code=status_code,
    )


@router.get("/agent-config", response_class=HTMLResponse)
def agent_config_page(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    """List every agent's current LLM config."""
    configs = AgentConfigService(session).list_configs()
    return _TEMPLATES.TemplateResponse(
        request=request, name="agent_config.html", context={"configs": configs}
    )


@router.get("/agent-config/{agent_name}", response_class=HTMLResponse)
def agent_config_edit_page(
    request: Request,
    agent_name: str,
    session: Annotated[Session, Depends(get_session)],
) -> HTMLResponse:
    """Render the edit form for one agent (404 if unknown)."""
    v = AgentConfigService(session).get_config(agent_name)  # NotFoundError → 404
    return _render_agent_config_edit(
        request,
        agent_name=v.agent_name,
        provider=v.provider or "",
        model=v.model or "",
        temperature="" if v.temperature is None else str(v.temperature),
        max_tokens="" if v.max_tokens is None else str(v.max_tokens),
        updated_at=v.updated_at,
    )


@router.post("/agent-config/{agent_name}", response_class=HTMLResponse)
def agent_config_save(
    request: Request,
    agent_name: str,
    session: Annotated[Session, Depends(get_session)],
    provider: str = Form(""),
    model: str = Form(""),
    temperature: str = Form(""),
    max_tokens: str = Form(""),
) -> Response:
    """Persist one agent's config, then redirect back (PRG). Invalid input → 400 + form."""
    svc = AgentConfigService(session)
    svc.get_config(agent_name)  # 404 before any write if the agent is unknown
    try:
        svc.update_config(
            agent_name,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except DomainValidationError as exc:
        return _render_agent_config_edit(
            request,
            agent_name=agent_name,
            provider=provider,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            error=str(exc),
            status_code=400,
        )
    return RedirectResponse(
        url=f"/dashboard/agent-config/{agent_name}?saved=1", status_code=303
    )
```

> If `dashboard.py` already imports `Response`/`HTMLResponse`, extend that import line rather than
> duplicating it.

- [ ] **Step 4: Run, expect PASS**

Run: `cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_dashboard.py -x`
Expected: PASS (all 6 tests).

```xml
<task id="4.1" wave="4">
  <files>apps/api/app/routers/dashboard.py, apps/api/tests/api/agent_config/test_agent_config_dashboard.py</files>
  <action>Add GET /dashboard/agent-config (list), GET /dashboard/agent-config/{agent_name} (edit form), POST /dashboard/agent-config/{agent_name} (validate → update_config → 303 PRG with ?saved=1; catch DomainValidationError → re-render form with status_code=400 and preserved inputs). Add the _model_hints + _render_agent_config_edit helpers and the required imports (Form, RedirectResponse, Response, service, provider catalog). POST calls get_config first so an unknown agent 404s before any write. TDD per steps.</action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/api/agent_config/test_agent_config_dashboard.py -x</verify>
  <done>All 6 HTTP tests pass: list 200, edit 200/404, POST 303+saved=1 & persists, invalid→400 with preserved input, unknown→404.</done>
</task>
```

---

### Task 5.1 — Full verify (lint + targeted suite)

```xml
<task id="5.1" wave="5">
  <files>apps/api/app/services/agent_config_service.py, apps/api/app/routers/dashboard.py, apps/api/app/core/agent_config_cache.py</files>
  <action>Run ruff on the changed files and the full agent_config + dashboard test set to confirm no regressions across the slice. Fix any lint/format findings on newly-written code (Rule 3).</action>
  <verify>cd apps/api && ruff check app && ../../.venv/bin/python -m pytest tests/core/test_agent_config_cache.py tests/api/agent_config -x -q</verify>
  <done>ruff clean on app/; cache + all agent_config/dashboard tests green.</done>
</task>
```

---

## Waves

| Wave | Tasks | Parallel? | Files disjoint |
|---|---|---|---|
| 1 | 1.1 requirements, 1.2 cache.invalidate | 2 parallel | requirements.txt · cache.py+its test |
| 2 | 2.1 service | single | services/ + agent_config test |
| 3 | 3.1 templates | single | templates/ only |
| 4 | 4.1 routes + HTTP tests | single | dashboard.py + dashboard test |
| 5 | 5.1 full verify | single | (verify only) |

Wave 2 depends on 1.2 (`invalidate`). Wave 4 depends on 2.1 (service) + 3.1 (templates rendered by
the HTTP tests). Wave 5 depends on all.

## Risks

- **First dashboard write route** (public contract) — commit with `RISK_WARN_CATEGORIES="public-contract"`.
- **Core cache file touched** — additive `invalidate()` only; rollback `git revert <sha>`.
- **`base_url` cleared on save** — intentional (design §7); only affects rows with a custom gateway
  (none in the default seed).
- **`from app.data` outside seed.py** — accepted deviation (plan decision); record in SUMMARY.

## Rollback

- Revert code: `git revert <sha>` for each task commit (no migration to undo).
- Remove the `python-multipart` pin line if the dep addition must be reverted.

## Status log

- 2026-07-02 — plan drafted from approved design.md + research-brief.md; 5 tasks / 5 waves.
