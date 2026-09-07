<!-- auto: bootstrap-xia2 (2026-07-09) — travel-pi FastAPI guidelines, tailored from CLAUDE.md
     Conventions/Design (the bundled templates/stacks/fastapi/guidelines.md is generic). Review,
     then move over .claude/rules/guidelines.md. -->

# Engineering Guidelines — travel-pi

## Code Style

- Python 3.10+ type hints; Pydantic v2. `datetime.now(timezone.utc)`, never `utcnow()`.
- Schemas extend `AppBaseModel` (`app/schemas/base.py`). Never raw dicts for request/response I/O.
- ORM models referenced via the `models.` namespace (e.g. `models.Hotel`) to avoid Pydantic-schema
  name collisions. ORM stays inside `repositories/`.
- `logging.getLogger(__name__)` — one module-scoped logger per file; never `print()`.
- Lint/format with `ruff` (`ruff check app scripts` / `ruff format app scripts`).

## Layer Discipline

- routers → services → repositories. Each layer has one job; do not leak concerns across it.
- Services raise domain exceptions (`NotFoundError`/`ConflictError`/`UpstreamError`), **never**
  `HTTPException`. Routers stay thin; repositories hold no logic.
- Agent tools / MCP are thin adapters over services — no business logic in the tool/MCP layer.

## Error Handling

- Guard clauses first — validate at function top with early returns.
- Map domain exceptions centrally in `main.py`; construct them from `exceptions.py`, not ad-hoc.
- In agent tools, map `AppError`/`ValueError` → `ToolException` so `ToolNode` surfaces a
  self-correctable error to the model. Log swallowed exceptions with component context.

## Data Access

- All persistence through `repositories/`; no ad-hoc queries in routers/services.
- **Session scope:** request path → `Depends(get_session)`; agent tools / background →
  `session_scope()` (or a `get_session_factory(url)`-bound sessionmaker). Never use the
  request-scoped session in background/tool code. `str(SQLAlchemy URL)` masks the password —
  bind isolated sessionmakers to the engine, don't rebuild from string.
- After any ORM schema change, rebuild `travel.db` or the whole suite fails (lifespan seeds the
  real DB; `create_all` won't add columns). Deterministic seed algorithm is load-bearing —
  don't change it.

## Async I/O & Performance

- Async **only** for real network I/O (`weather_service`, `routing_service`). Everything else is
  sync — do not make handlers async speculatively.
- Fuzzy name resolution for free-text city/country via `core/text.py` (folds VN diacritics);
  unknown city → `count: 0`, not 404. `weather_service.geocode_city` memoises process-wide.

## Agent / LLM

- Provider-agnostic via `init_chat_model()`; tests run on `FakeLLM` (no network).
- Prompt / `active.yaml` edits are NOT hot-reloaded — the graph is baked at lifespan startup;
  force a rebuild (`touch app/main.py`) to see prompt changes.
- Log token usage for AI paths, including failure cases. Never log PII (passenger/guest
  name/email/phone) — log non-PII identifiers only.

## Testing

- `make test` (SQLite, fast) and `make test-docker` (Postgres parity, Python 3.12). Test happy
  path + error/edge + boundary. No live network — use `FakeLLM` / mocks for I/O.
- Tool/service tests: pin `DATABASE_URL=sqlite:///:memory:` (the local `.env` carries
  `OPENAI_API_KEY=test` and a Postgres URL that break LLM tests / TestClient-lifespan setup).
- Adding a public HTTP endpoint or widening the MCP tool surface is a public-contract gate —
  authorize commits with `RISK_WARN_CATEGORIES="public-contract"` when the corroboration hook fires.

## Logging

- Module-scoped logger per file; prefix messages with component context.
- Never log secrets/tokens or PII.

## Design (UI work)

- Two design systems, one per surface. Web app (`apps/web/`, Next.js): repo-root `DESIGN.md` +
  `PRODUCT.md`, build from `apps/web/src/components/ui/` primitives + Tailwind `@theme` tokens.
  API dashboard (`apps/api/`, `/dashboard/*`): `apps/api/DESIGN.md` + `apps/api/PRODUCT.md`.
  Extend the system — never route around it. Use `/impeccable` for design tasks.
