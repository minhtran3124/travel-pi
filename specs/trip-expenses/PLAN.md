---
slug: trip-expenses
status: shipped
owner: Minh Tran
created: 2026-06-25
---

# Trip Expenses — On-trip Spend Ledger

The data layer for a future travel-assistant to record and categorise real spending during a
trip ("breakfast 50,000 VND") and answer "how much of my budget have I spent". A new
`expenses` child-resource of `Trip`, independent of the booking-based `/budget` feature, with
multi-currency support normalized to USD.

See `SUMMARY.md` for the intake lane, resolved design decisions (A + A), and rollback.

## 1. Motivation

Today "spent" is derived only from linked flight/hotel **bookings** (`trip_service`
`_spend_by_category`); there is no way to record manual, on-the-ground spending. The assistant
scenario needs a per-trip expense ledger: amount + currency + category + when, aggregated and
comparable to the trip budget.

## 2. Non-goals

- **NLU / chatbot parsing** of free text ("breakfast 50k" → amount/category). That is the
  agent layer, built later on top of these endpoints.
- **Changing the existing `/budget` contract** or its booking-based spend logic.
- Per-expense receipts/attachments, splitting between travelers, recurring expenses.
- Live FX — reuse the existing seeded snapshot (`app/data/fx.py` → DB → `FxRepository`).

## 3. Success criteria

- `POST /trips/{trip_id}/expenses` records an expense in any supported currency; server
  normalizes to USD and stores the `fx_rate` used.
- `GET /trips/{trip_id}/expenses` lists/filters (category, currency, date range), paginated.
- `GET /trips/{trip_id}/expenses/summary` returns total (USD), per-category, per-currency
  breakdowns, plus a planned-vs-actual rollup (budget caps + booked + expense actuals).
- `GET/PATCH/DELETE /trips/{trip_id}/expenses/{expense_id}` work; unknown trip/expense → 404;
  unknown currency → 404 with supported-codes hint; `amount <= 0` → 422.
- `make test` and `make test-docker` green.

## 4. Categories (decided; easily extendable)

`ExpenseCategory(str, Enum)`: `food, transport, accommodation, activities, shopping,
entertainment, health, other`. New `enum` in `app/enums.py` (distinct from the booking-bucket
`BudgetCategory`).

## 5. Tasks

### Task 1.1 — Enum + Expense model + migration

```xml
<task id="1.1" wave="1">
  <files>app/enums.py, app/db/models/expense.py, app/db/models/__init__.py, alembic/versions/, travel.db</files>
  <action>Add ExpenseCategory(str, Enum) {food, transport, accommodation, activities, shopping, entertainment, health, other} to app/enums.py. Add Expense(UUIDBase) ORM model in app/db/models/expense.py: trip_id (String, indexed, FK→trips.id), category (String), amount (Float), currency (String, ISO 4217), amount_usd (Float), fx_rate (Float), description (String|None), occurred_at (String, ISO-8601), deleted_at (String|None soft-delete). Export Expense in app/db/models/__init__.py. Generate the Alembic migration with `.venv/bin/alembic revision --autogenerate -m "add expenses table"`, then review/edit (add index on trip_id, partial soft-delete index following the booking confirmation_code pattern). Rebuild dev DB: `rm -f travel.db && .venv/bin/alembic upgrade head && make seed` (per stale-travel-db memory).</action>
  <verify>.venv/bin/alembic upgrade head && .venv/bin/python -c "from app.db import models; assert hasattr(models, 'Expense'); from app.enums import ExpenseCategory; print('ok')"</verify>
  <done>Migration applies clean on SQLite; Expense importable via models. namespace; ExpenseCategory present; travel.db rebuilt.</done>
</task>
```

### Task 2.1 — Repository (parallel with 2.2)

```xml
<task id="2.1" wave="2">
  <files>app/repositories/expense.py, tests/api/expense/test_expense_repo.py</files>
  <action>ExpenseRepository(Repo) using the dual-mode base (app/repositories/base.py): add(expense), get(id_), list(trip_id, *, category=None, currency=None, date_from=None, date_to=None), update(id_, **fields), soft_delete(id_, when). Filter deleted_at IS NULL on all reads. Materialize Pydantic Expense inside the session context (_row_to_expense) to avoid detached rows — mirror app/repositories/saved_place.py. Tests: create→get, list filters (category/currency/date range), soft_delete hides row, update mutates. Use a TripRepository-seeded trip or insert a trip row first.</action>
  <verify>.venv/bin/pytest tests/api/expense/test_expense_repo.py -x</verify>
  <done>CRUD + every filter branch covered and green.</done>
</task>
```

### Task 2.2 — Schemas (parallel with 2.1)

```xml
<task id="2.2" wave="2">
  <files>app/schemas/expense.py, tests/api/expense/test_expense_schema.py</files>
  <action>Pydantic v2 schemas extending AppBaseModel: ExpenseCreate {category: ExpenseCategory, amount: float (gt=0), currency: str, description: str|None=None, occurred_at: str|None=None}; ExpenseUpdate (all optional); Expense(ExpenseCreate) adds id, trip_id, amount_usd, fx_rate, created_at + computed short_code "EXP-XXXXXX" (prefixed_code helper, mirror SavedPlace); ExpenseListResponse(PagedResponse[Expense]). Summary schemas: CategoryExpense {category, total_usd, count}; CurrencyExpense {currency, total_original, total_usd, count}; ExpenseBudgetActuals {total_cap: float|None, booked_spent, expense_spent, total_spent, total_remaining: float|None, over_budget: bool}; ExpenseSummary {expense_count, total_usd, by_category: list[CategoryExpense], by_currency: list[CurrencyExpense], budget: ExpenseBudgetActuals}. Validator: uppercase+strip currency. Tests: amount<=0 rejected, currency normalized, short_code format.</action>
  <verify>.venv/bin/pytest tests/api/expense/test_expense_schema.py -x</verify>
  <done>Schema validation tests pass; request/response split clean.</done>
</task>
```

### Task 3.1 — Service

```xml
<task id="3.1" wave="3">
  <files>app/services/expense_service.py, tests/api/expense/test_expense_service.py</files>
  <action>ExpenseService(session: Session): builds ExpenseRepository, TripRepository (validate trip exists → NotFoundError 404), FxRepository (normalize amount→USD: rate = fx.rate("USD")/fx.rate(currency); amount_usd = round(amount*rate, 2); store fx_rate; unknown currency → NotFoundError with valid_codes() hint, mirror CurrencyService._resolve_code). Methods: create(trip_id, ExpenseCreate) [default occurred_at=now ISO; gen uuid], get(trip_id, expense_id) [404 if missing or wrong trip], list(trip_id, filters), update(trip_id, expense_id, ExpenseUpdate) [recompute amount_usd/fx_rate if amount or currency changed], delete(trip_id, expense_id) [soft delete], summary(trip_id) → ExpenseSummary: aggregate by_category/by_currency/total_usd from the ledger, and build budget actuals by calling TripService(session).get_trip_budget(trip_id) for total_cap + booked total_spent, then expense_spent=sum(amount_usd), total_spent=booked+expense, total_remaining=total_cap-total_spent (None if no caps), over_budget flag. Use the _money/round-half-up convention from trip_service. Export get_expense_service(session=Depends(get_session)) + ExpenseDep alias. Tests (AsyncMock not needed — sync): happy create + FX normalization (50000 VND → ~1.97 USD), 404 unknown trip, 404 unknown currency, summary math (multi-currency, by-category), budget actuals with and without caps.</action>
  <verify>.venv/bin/pytest tests/api/expense/test_expense_service.py -x</verify>
  <done>Service unit tests pass incl. FX normalization, 404 paths, summary + actual-vs-planned math.</done>
</task>
```

### Task 4.1 — Router + registration

```xml
<task id="4.1" wave="4">
  <files>app/routers/expenses.py, app/routers/main.py, tests/api/expense/test_expense_api.py</files>
  <action>APIRouter under /trips/{trip_id}/expenses using ExpenseDep + PaginationDep (mirror app/routers/places.py saved-place endpoints): POST "" → 201 Expense; GET "" → ExpenseListResponse with Query filters category/currency/date_from/date_to; GET "/summary" → ExpenseSummary (DECLARE BEFORE the /{expense_id} route to avoid capture); GET "/{expense_id}" → Expense; PATCH "/{expense_id}" → Expense; DELETE "/{expense_id}" → 204. Use error_responses(404, 422). Register router in app/routers/main.py via include_router (after trips). Tests via the `client` fixture: 201 create, 200 list/summary, 404 unknown trip + unknown expense, 422 amount<=0, route ordering (/summary not swallowed).</action>
  <verify>.venv/bin/pytest tests/api/expense/test_expense_api.py -x</verify>
  <done>All endpoint tests green; OpenAPI shows the new routes; /summary resolves before /{expense_id}.</done>
</task>
```

### Task 5.1 — Integration e2e + full suite

```xml
<task id="5.1" wave="5">
  <files>tests/api/expense/test_expense_e2e.py</files>
  <action>End-to-end via client fixture: create a trip → POST /budget caps → POST expense {amount:50000, currency:"VND", category:"food", description:"breakfast"} → assert amount_usd ≈ round(50000/25400, 2) → add a second USD expense → GET /expenses (list both) → GET /expenses/summary: assert total_usd = sum of both amount_usd, by_category has food, by_currency has VND+USD, budget.expense_spent matches, budget.total_remaining = total_cap - (booked + expense). Then PATCH amount and re-check summary, DELETE one and confirm it drops from totals. Finish: run `make test` (full SQLite suite) and `make test-docker` (Postgres parity).</action>
  <verify>.venv/bin/pytest tests/api/expense/test_expense_e2e.py -x</verify>
  <done>e2e green; `make test` full suite green; `make test-docker` green.</done>
</task>
```

## 6. Waves

| Wave | Tasks | Parallelism | Files disjoint? |
|------|-------|-------------|-----------------|
| 1 | 1.1 enum+model+migration | single | — |
| 2 | 2.1 repository, 2.2 schemas | 2 parallel | yes (repositories/ + repo test vs schemas/ + schema test) |
| 3 | 3.1 service | single | — |
| 4 | 4.1 router + main.py wiring | single | — |
| 5 | 5.1 e2e + full suite | single | — |

## 7. Risks

- **Public-contract hard gate** on new endpoints — commit with
  `RISK_WARN_CATEGORIES="public-contract"` (see SUMMARY → Hard gates). Additive only.
- **Stale travel.db** after the schema change breaks the whole suite — rebuild in task 1.1
  (`rm travel.db && alembic upgrade head && make seed`).
- **Docker py3.12 eager annotations** — keep model field annotations import-safe; run
  `make test-docker` in task 5.1.
- **FX rounding drift** — reuse the existing round-half-up `_money` convention; assert with a
  tolerance (`pytest.approx`) in tests, not exact float equality.
- **Route capture** — `/summary` must be declared before `/{expense_id}` (covered in 4.1).

## 8. Status Log

- 2026-06-25 — Plan drafted (status: proposed). Awaiting go-ahead to execute wave 1.
- 2026-06-25 — All waves executed and verified. status: shipped.
