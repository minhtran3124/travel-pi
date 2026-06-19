# trip-budget — Escalations

## Design-shape fork (low confidence) — confirm intent before PLAN/code

- **Date:** 2026-06-19
- **Lane:** normal (migration hard gate waived by A0 `ensure_column` convention, by analogy).
- **Why escalated:** the source (`AGENT_IMPROVEMENTS.md` #12) is two bullet lines and leaves
  three materially different design choices open. Two competent engineers would build
  different schemas/serializers/enforcement:
  1. **Target shape** — a single scalar `budget_target` (USD) on the trip, **or** per-category
     caps (`flights/hotels/activities/buffer`). Different column(s), `POST` body, and 409 logic.
  2. **"planned" source** — reuse the existing `estimate_trip` category breakdown as the
     "planned" column (no extra data model), **or** add a per-item planned cost (second
     migration, bigger scope).
  3. **Enforcement** — hard `409` at `POST /trips/{id}/items` when a linked booked item would
     push `total_spent` past target, **or** advisory-only (surface `over_budget`, never block).
- **Decision needed (human):** confirm shape (1), "planned" source (2), and enforcement (3).
  My proposed defaults: scalar total target · reuse `estimate_trip` breakdown · hard 409 at
  item-add. These keep the change additive and reuse existing computation.
- **Status:** ✅ RESOLVED 2026-06-19 (user via AskUserQuestion). Decisions:
  1. **Target shape →** per-category caps (`flights/hotels/activities/buffer`).
  2. **"planned" source →** reuse `estimate_trip` category breakdown (no per-item cost field).
  3. **Enforcement →** hard 409 at `POST /trips/{id}/items` when a linked booked item pushes a
     category's spent past that category's cap.
  PLAN/code unblocked; folded into SUMMARY.md → Resolved decisions. Routing to `/writing-plans`.
- **Default-on-no-response:** n/a — answered.
