# close-product-loop-s1-booking-ui — Research Brief

Depth: **Deep** (intake lane `high-risk`; not upgraded, not lowered).
Waiver: none. Design under research: `specs/close-product-loop/design.md` §5 S1 (user-approved 2026-09-08).

## Bottom Line

| Field | Value |
|---|---|
| **Recommendation** | **Reuse existing** — extend three established patterns (a DB-hitting FastAPI dependency, an Alembic `batch_alter_table` column+index add, and the FE `throwOn409` status-branch) rather than introduce any new mechanism. |
| **Why this is the lightest credible path** | Every piece S1 needs already has exactly one precedent in this repo, and the only genuinely new artifact is the two web pages themselves. |
| **Confidence** | 88% |
| **Next step** | Amend the approved design on the three points in "Design amendments" below, then `writing-plans`. |

## Repo Snapshot

| Field | Detected |
|---|---|
| Repo type | Monorepo (pnpm workspaces + Turborepo): FastAPI API + Next.js web |
| Primary language + runtime | Python 3.12 in Docker (`apps/api/Dockerfile:1`), 3.14 in the local venv; TypeScript on Node 24 |
| Frameworks / platforms | FastAPI `>=0.110,<0.137`, SQLAlchemy `2.0.x`, Alembic `>=1.13,<2`, Pydantic `2.x`; Next 16.2.9, React 19.2.4, TanStack Query 5.101, openapi-fetch 0.17, next-intl 4.13 |
| Relevant packages | `app/services/booking_service.py`, `app/repositories/booking.py`, `app/core/auth.py`, `app/core/rate_limit.py`, `apps/web/src/lib/api/*`, `src/lib/query/*` |
| Detectable versions | `apps/api/requirements.txt`, `apps/web/package.json`; vitest 2.1, Playwright 1.49 |
| Important constraints | `CLAUDE.md` (venv at repo root, Node 24, run BE cmds from `apps/api/`); `rules/auto-correct-scope.md` Rule 4 (schema + API contract + authz are STOP-class, already authorized by the approved design); branch isolation required |

## Feature Understanding and Assumptions

- **Requested feature:** premium-gated flight/hotel booking screens on the web, with bookings linked to a trip.
- **What success appears to mean:** a premium user searches and books from `/flights` or `/hotels`, the booking appears on the trip's Bookings tab and in the budget; a free user searches, is refused at book time, and sees an upgrade dialog.
- **Assumptions from the request:** the tier gate belongs on the REST route (design decision); simulated inventory stays; no payment.
- **Assumptions still needing confirmation:** none. The one open question — whether `booked_total` may diverge from `total_spent` — was confirmed by the user on 2026-09-08: both are shown, labelled distinctly, and the existing per-item logic is untouched.

## Evidence Ledger

| Label | Evidence |
|---|---|
| `Local` | `app/core/auth.py:44-57,112,150-151` — `AuthUser` (with `role`), `CurrentUserDep`; **no tier/role dependency exists** |
| `Local` | `app/routers/admin.py:58-61` — the only role check today is **inline in the route** (`raise ForbiddenError`), not a dependency |
| `Local` | `app/core/rate_limit.py:36-37,143-165` — the precedent for a **DB-hitting dependency factory** (`session` + `auth_user` injected into a nested `dependency`) |
| `Local` | `app/exceptions.py` + `app/core/errors.py:29-39,44-60` — domain exceptions, envelope `{error, message, status_code, path, request_id, hint?}`; **no `code` field**, `error` = exception class name, `_error_body` omits absent keys |
| `Local` | `app/schemas/error.py:59-71` — `error_responses(*codes)` **raises KeyError** for a status not in `_DESCRIPTIONS` (401/403/404/409/422/502 present, so 403 is fine) |
| `Local` | `app/services/booking_service.py:250,276,325-347,354,400-425` — `_replay` first, then build Pydantic `Booking`; `currency`/`total_price` come from the resolved inventory row, never the client |
| `Local` | `app/repositories/booking.py:17-33,163-186` — `_row_to_booking` and `add` map field-by-field; **both must learn `trip_id`** |
| `Local` | `app/services/booking_service.py:57-95` — list filtering (`q`/`type`/`sort`) is done **in Python** over `list_all(user_id)`; no SQL filter beyond `user_id` exists |
| `Local` | `app/db/models/trip.py:48` — `trip_items.trip_id` is `String, nullable=False, index=True`, **no FK**: the precedent for `bookings.trip_id` |
| `Local` | `alembic/versions/c7f1a9d4e6b2_*.py:58-61` — add column + `create_index` inside one `batch_alter_table`; single head is `a7c3e9f1b2d4`; `ensure_column`/`app/crud/` **do not exist** |
| `Local` | `app/services/trip_service.py:375-412,443-470` — `_spend_by_category` walks `trip.items`, skips `booking_id is None`, skips cancelled, sums **per item**; `_build_budget` is where `booked_total` belongs |
| `Local` | `app/tools/flight_tools.py:384`, `app/tools/hotel_tools.py:488` — agent tools call `BookingService` **directly**, bypassing the route; `app/mcp/server.py:43-51` + `app/tools/registry.py:78` exclude all four booking tools from MCP |
| `Local` | `tests/conftest.py:66-93` — `get_current_user` globally overridden, no `users` row ⇒ tier `"free"`; **no premium fixture**; `tests/api/agent/test_quota.py:52-56` sets tier via `UserRepository(s).upsert_tier(uid, "premium")` |
| `Local` | `tests/db/test_content_translations_migration.py:44-60` — the migration round-trip test template (downgrade → assert absent → upgrade → assert → downgrade) |
| `Local` | `apps/web/src/lib/api/errors.ts` — `ConflictError` base (documented 409-only) + `throwOn409(response, error, Ctor)`; three call sites, none composing two |
| `Local` | `apps/web/src/lib/api/client.ts:10-13,26-27,46-52` — `unwrap()` **discards `response`**; `IDEMPOTENT_POST_PATHS` covers only `POST /trips` and `POST /trips/{id}/items` |
| `Local` | `apps/web/src/lib/query/places.ts:81-90` — the one hook that reads `response` and branches on status before `throw error` |
| `Local` | `apps/web/src/components/chat/panel/{FlightsPanel,HotelsPanel}.tsx` — one prop each, rows fully presentational, only coupling is `useTranslations("Panel")` |
| `Local` | `apps/web/src/app/trips/[tripId]/page.tsx:23-28,54-57` + `AppShell.tsx:15-19` — literal `Tab[]` list and `NAV_LINKS` const are the two edit points |
| `Local` | `apps/web/src/test/setup.ts:24-45`, `src/messages.parity.test.ts:26-38` — MSW with `onUnhandledRequest:"error"`; parity test compares key paths only, never values |
| `Local` | `app/data/hotels.py` — 183 seeded rows, all `"currency": "USD"`; `app/schemas/flight.py:65-66` defaults to USD ⇒ `booked_total` is a single-currency scalar today |
| `Inference` | Two trip items pointing at one booking double-count in `total_spent` today (the `resolved` dict dedupes the *fetch*, the loop sums *per item*) — read from the code, not observed at runtime |
| `Docs` | Not applicable — see Docs Findings |

## Local Findings

- **Relevant files, modules, scripts, docs, tests:** as cited above; BE tests under `apps/api/tests/api/{booking,flight,hotel,trip}/` and `tests/db/`; FE tests colocated plus `playwright/{auth.setup,trip-smoke}.spec.ts`.
- **Existing abstractions or extension points:**
  1. `rate_limit(...)` is the model for `require_premium` — a factory returning a nested dependency that takes `session` + `auth_user`.
  2. `_filter_and_sort` is the model for the `trip_id` filter (in-Python, no new repo query).
  3. `_build_budget` is the single home for `booked_total`.
  4. `throwOn409` is the model for `throwOn403`.
- **Conventions worth preserving:** domain exceptions not `HTTPException`; server-resolved tier never from the body; prices/currency from the inventory row; `batch_alter_table` for every column add; MSW handlers per test; every new string in both message files.
- **What can likely be reused:** the whole error/dependency/migration/test scaffolding, the flight and hotel row renderers (extractable — they are pure, their only coupling is the `Panel` namespace), `Modal`/`ConfirmDialog`/`EmptyState`/`Field`/`Spinner`.
- **What appears missing locally:** a premium test fixture; a status-403 FE error type; `Idempotency-Key` coverage for the two book routes; `trip_id` on the booking ORM row, repo mapping, request schemas and read model.

Five findings that matter more than the rest:

1. **The `code: "premium_required"` field in the design does not fit the error envelope.** No response body in this API carries a `code`; the discriminator is `error` (the exception class name), and the FE already branches on `response.status` alone (`throwOn409`; `useAgentStream.ts:252` on 403). Adding `code` would widen the shared error contract for every endpoint to buy nothing.
2. **The route gate does not gate the chatbot.** `app/tools/flight_tools.py:384` calls `BookingService` directly, so `require_premium` on the route is purely the new UI path's gate; the agent stays gated by the supervisor. Two gates in two places is the existing shape, not a regression introduced here.
3. **Booking was never on the MCP surface** (`registry.py:78` `_DESTRUCTIVE`), so nothing in S1 changes what MCP exposes.
4. **`Idempotency-Key` is not sent for book requests today.** The FE whitelist covers only the two trips paths, so a double-click on the new Book button would create two bookings even though the BE supports replay.
5. **`booked_total` and `total_spent` will legitimately differ.** Today spend counts a booking only if some itinerary item references it, and counts it once per referencing item. A `trip_id`-based `booked_total` counts every booking on the trip exactly once. That is the point of the field, but the two numbers appearing side by side on the Budget tab needs a deliberate label, or it reads as a bug.

## Upstream Findings

- **Repositories inspected:** none. Every mechanism S1 needs has a working in-repo precedent (dependency factory, migration shape, status-branching error helper), so upstream modelling would add no information a local citation does not already give.
- **Pattern or capability already present upstream:** not applicable.
- **Files, modules, or areas worth modeling:** the four in-repo extension points listed above.
- **How closely the upstream pattern matches this repo:** not applicable.
- **Any upstream gaps or uncertainties:** none; this is a deliberate scope call, not a failed search.

## Docs Findings

- Not applicable: S1 adds no dependency, integrates no external system, and relies on no version-specific API. FastAPI `Depends`, Alembic `batch_alter_table`, and openapi-fetch's `{data, error, response}` are all already used in this repo at the pinned versions.

## Recommendation

- **Primary recommendation:** **reuse existing** — implement S1 entirely as extensions of the four in-repo patterns named above.
- **Why this is the lightest credible path:** the only net-new files are the two page components, one extracted card per domain, one dependency, one migration, and one FE error type. Everything else is an edit to a file that already does the same job for a neighbouring case.
- **Why the next-best alternative lost:** putting the tier gate in `BookingService` instead of on the route would cover every caller including the agent tools, but the agent path is already gated by the supervisor, and a service-level raise would change what a free user sees in chat — perturbing agent behaviour and the eval goldens for a hole that does not exist. The route dependency keeps the blast radius inside the new UI path.
- **What would change this recommendation:** evidence that a non-agent, non-REST caller reaches `BookingService.book_*` (then the gate must move down into the service), or a product decision that free users may book (then the gate disappears and only the `trip_id` work remains).

### Design amendments — all three DECIDED by the user 2026-09-08 and written into the design

1. **DECIDED — drop `code: "premium_required"`.** Raise a distinct exception subclass (for example `PremiumRequiredError(ForbiddenError)`) so the envelope's `error` field carries the discriminator, and let the FE branch on `response.status === 403`. No envelope change, no OpenAPI-wide field.
2. **DECIDED — add `Idempotency-Key` for the book routes** to `IDEMPOTENT_POST_PATHS` (`apps/web/src/lib/api/client.ts:10-13`). Without it the new UI can double-book.
3. **DECIDED (show both, labelled) — state the `booked_total` semantics on the Budget tab**: "booked on this trip" (every booking with this `trip_id`, cancelled excluded, counted once) versus `total_spent` ("counted in the itinerary"). Confirm the divergence is intended.

## Risks, Unknowns, and Follow-Up Questions

- **Technical risks:**
  - Non-USD inventory would silently make `booked_total` a mixed-currency sum; nothing enforces one currency per trip.
  - `error_responses(403)` is safe (403 is in `_DESCRIPTIONS`), but adding an undeclared status elsewhere raises `KeyError` at import — keep to declared codes.
  - Extracting the flight/hotel rows must preserve the `Panel` translation namespace, `hhmm()`'s UTC pinning, and the `ring-2 ring-lime` cheapest marker, or five existing panel tests fail (`FlightsPanel.test.tsx` pins `TZ` on line 3, before imports).
  - Any ORM schema change invalidates a stale local `travel.db`; the suite fails wholesale until it is rebuilt, and a seed-default change stays invisible on an existing DB.
  - `ruff-on-edit` deletes an import added before its first use — add import and usage in the same edit.
  - Python 3.12 in Docker versus 3.14 locally: run `make test-docker` before shipping.
- **Evidence gaps:** none material. The currency question the design left open is **closed**: all 183 seeded hotel rows are `"currency": "USD"` (`app/data/hotels.py`, the only distinct value) and `Flight.currency` defaults to `"USD"` (`app/schemas/flight.py:65-66`), so `booked_total` can be a single scalar today. It stops being one the moment non-USD inventory is seeded.
- **Version uncertainties:** none material; all versions read from manifests.
- **Follow-up questions for the user:** none outstanding. Both were asked and answered on
  2026-09-08: (1) show `booked_total` beside `total_spent` with distinct labels, leaving the
  existing per-item logic untouched; (2) a distinct `PremiumRequiredError` class replaces the
  `code` field.

## Source Pack

- **Local files read:** `apps/api/app/core/{auth,errors,rate_limit}.py`, `app/exceptions.py`, `app/schemas/{error,trip,booking,flight,hotel}.py`, `app/routers/{flights,hotels,bookings,trips,admin,agent,destinations}.py`, `app/services/{booking_service,trip_service,quota_service}.py`, `app/repositories/{booking,user}.py`, `app/db/models/{booking,trip}.py`, `app/tools/{registry,flight_tools,hotel_tools}.py`, `app/mcp/server.py`, `app/enums.py`, `alembic/versions/{c7f1a9d4e6b2,d2f4b6a8c0e1,a7c3e9f1b2d4}*.py`, `tests/conftest.py`, `tests/api/agent/test_quota.py`, `tests/api/admin/test_admin_tier.py`, `tests/db/test_content_translations_migration.py`, `tests/infra/test_errors.py`; `apps/web/src/lib/api/{client,errors,keys}.ts`, `src/lib/query/{bookings,places,shortlist,items}.ts`, `src/lib/stream/panel.ts`, `src/components/chat/panel/{FlightsPanel,HotelsPanel,registry,PanelIntlProvider}.tsx` + their tests, `src/components/ui/{Modal,ConfirmDialog,EmptyState,Field,Button,Tabs}.tsx`, `src/components/AppShell.tsx`, `src/app/{layout,bookings/page,places/page,trips/[tripId]/page}.tsx`, `src/components/trips/expenses/ExpensesTab.tsx`, `src/test/{setup,msw}.ts`, `src/messages.parity.test.ts`, `messages/{en,vi}.json`, `vitest.config.ts`, `playwright/{auth.setup,trip-smoke}.spec.ts`; `docs/solutions/INDEX.md`, `critical-patterns.md`, `docs/reviews/2026-09-02-deep-review.md`, `CLAUDE.md`, `specs/close-product-loop/design.md`
- **Upstream repositories or pages checked:** none found
- **Official docs domains or pages checked:** none (local-only; no external surface)

## Evidence Boundary

> **Confirmed from artifacts:** the absence of a `code` field and of a tier dependency; the inline admin role check; the `rate_limit` dependency-factory precedent; the single Alembic head and the `batch_alter_table` column+index precedent; the absence of `ensure_column`; `_spend_by_category`'s per-item summation and its skip of unlinked bookings; agent tools calling `BookingService` directly; booking tools excluded from MCP; `unwrap()` discarding `response` and `throwOn409` being the only status branch; the book routes missing from the FE `Idempotency-Key` whitelist; the panel rows' single coupling to the `Panel` namespace; MSW with `onUnhandledRequest:"error"`; the parity test comparing key paths only; no premium test fixture.
>
> **Inferred from patterns:** that two items referencing one booking double-count in `total_spent` (read from the loop, not executed); that extracting the rows will keep the five panel tests green if the listed invariants hold; that `require_premium` modelled on `rate_limit` will compose cleanly with `CurrentUserDep` on the two book routes.
>
> **Not checked:** runtime behaviour of any of the above (nothing was executed — this was a read-only pass); the Playwright suite's current pass/fail state; whether `upsert_tier` has a route-level equivalent usable from a test client.
