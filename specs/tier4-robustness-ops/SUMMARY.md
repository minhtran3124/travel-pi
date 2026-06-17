<!--
  Initiative-level intake record. Header block is machine-read by
  hooks/risk-corroboration.sh (Lane:) and the trust-metrics ledger.
  Per-item stories get their own specs/<slug>/SUMMARY.md once scope is chosen.
-->

# tier4-robustness-ops — Summary

Lane: high-risk
Confidence: low
Reason: Bundle of 5 independent ops items spanning data-model (soft-delete trips), public contracts (new endpoints/headers/operationIds), existing-behavior changes (idempotency, DELETE hard→soft) and multiple domains — 4+ flags as a whole; and the scope is ambiguous (which items, what order).
Flags: data-model, public-contract, existing-behavior, multi-domain
Affects: all routers (operationId), bookings + trips (idempotency, soft-delete), app infra (/healthz, /readyz)
Input-type: new initiative

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane.

### Intent

> Tier 4 — Robustness & ops (less glamorous, real-world correctness)
>
> - Idempotency on every mutating endpoint, not just `/flights/book` and `/hotels/book` — `cancel`, trip mutations, future `book` endpoints, batch.
> - Rate-limit headers in responses (`X-RateLimit-*`) — even if not enforced, agents read these and self-throttle.
> - `/healthz` / `/readyz` — separates app health from upstream (ORS) availability; useful for agent retry logic.
> - OpenAPI `operationId` — pin stable operation IDs on every route so MCP/codegen names stay stable across refactors. (None set today.)
> - Soft-delete for everything that matters — bookings already do this; trips should too (`DELETE /trips/{id}` exists — confirm it's soft, not hard).

## What changed

All 5 Tier-4 items shipped on `feat/tier4-robustness-ops` (branched off v2), built lowest-risk first:
1. **Health** — `GET /healthz` (liveness) + `GET /readyz` (DB ping + ORS routing-provider status; degrades to `not_ready` instead of 500). New `app/routers/health.py`, `BookingService.ping()`.
2. **operationId** — pinned every route's operationId to its handler name via one `generate_unique_id_function` in `app/main.py` (renamed the `list_cities` collision in places.py → `list_place_cities`).
3. **Idempotency** — `Idempotency-Key` replay on `POST /trips` + `POST /trips/{id}/items` (mirrors the booking pattern; column + UNIQUE partial index + migration). PUT/DELETE/cancel already idempotent (out of scope).
4. **Rate-limit headers** — informational, unenforced `X-RateLimit-*` on every response (waiver-backed; `rate_limit_nominal` setting).
5. **Soft-delete trips** — `DELETE /trips/{id}` stamps `deleted_at` (keeps the row + items), all trip reads filter `deleted_at IS NULL`; clears `idempotency_key` on tombstone so keys recycle.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Full suite | `.venv/bin/python -m pytest tests/ -q` | 0 | 570 passed (560 baseline; +10) |
| Lint | `ruff check app` | 0 | All checks passed |
| Format (changed) | `ruff format --check app/crud/trip.py app/routers/health.py app/main.py app/services/trip_service.py` | 0 | already formatted |

### Deviations

- Rule 1 — Renamed `list_cities` → `list_place_cities` in `app/routers/places.py` (operationId collision). Commit `00fde46`.
- Rule 1 — 409 on `Idempotency-Key` reused across trips (cross-trip leakage). Commit `1ff0fea`.
- Rule 1 — Soft-delete clears `idempotency_key` + `/readyz` try/except (final-review P1/P2). Commit `2c89787`.

### Review gates

- Per-story spec + quality review (sonnet) ✅ on all 5.
- Final adversarial correctness review (sonnet, whole diff) — found 2 cross-story bugs (idempotency+soft-delete 500; /readyz 500-on-DB-down), both fixed + test-locked (`2c89787`).
- Final intent review (sonnet, blind to PLAN) — all 5 items faithful, no excess/gaps.

### Rationale

Classified as a **new initiative**, not one change: the five items are independent, land in
different layers, and have materially different risk. Per `rules/orchestration.md` an initiative
is broken into per-item stories, each with its own intake + SUMMARY + (if signalled) PLAN. The
bundle is escalated because scope is ambiguous — the user must pick which items and in what order
before any code is touched.

### Per-item risk preview (to inform the scope decision)

| Item | Likely lane | Notes |
|---|---|---|
| `/healthz` + `/readyz` | normal | 2 new additive public endpoints; cleanest, lowest-risk. Good first slice. |
| OpenAPI `operationId` | normal (high-blast) | Touches **every** router file; mechanical but wide. Additive metadata. |
| Idempotency everywhere | normal | Extends the existing `Idempotency-Key` pattern to `cancel` + trip mutations; existing-behavior + contract. |
| Soft-delete trips | normal→high-risk | Changes `DELETE /trips/{id}` from **hard** to **soft** delete (confirmed hard today) — data retention + behavior + contract change. The one item with real data semantics. |
| Rate-limit headers | ⚠️ conflicts with policy | `CLAUDE.md` explicitly scopes the project as "no auth, ORM, pagination, or **rate limiting**" (`mock-api-spec.md` §1). Headers-only (unenforced) is borderline; needs an explicit policy waiver before building. |

### Alternatives considered

- Treat as one PLAN — rejected: 5 disjoint items, different lanes/risk; one plan would violate the wave/file-overlap and lane model.

### Rollback

- Per-commit `git revert <sha>` (all additive). Story 5 (soft-delete) high-risk rollback: `git revert f8b2a64 2c89787` — the `deleted_at` / `idempotency_key` columns are additive & nullable, so reverting the code restores hard-delete with no down-migration; no data lost either direction.
