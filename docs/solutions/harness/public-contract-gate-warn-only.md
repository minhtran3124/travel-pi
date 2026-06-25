---
problem_type: knowledge
module: harness/intake
tags: risk-corroboration, public-contract, feature-intake, openapi, lane, hook, warn-only
severity: standard
applicable_when: Committing a normal-lane change that touches OpenAPI surface (router tags, per-route `responses=`, response models) but whose generated contract you can prove is unchanged or strictly superset
affects:
  - .claude/hooks/risk-corroboration.sh
  - .claude/skills/feature-intake/SKILL.md
supersedes: null
confidence: high
confirmed_at: 2026-06-23
---
## Applicable When

A `normal`-lane task edits FastAPI router metadata that feeds OpenAPI — `tags=`,
`responses=error_responses(...)`, or response models — and you have evidence (a before/after
`app.openapi()` diff) that the generated contract is byte-identical or strictly superset. The
commit is blocked by `risk-corroboration.sh` on the `public-contract` category even though no
real contract regression exists.

## Pattern

`risk-corroboration.sh` corroborates the declared `Lane:` in `specs/<slug>/SUMMARY.md` against
the staged diff. It pattern-matches the diff for hard-gate signals; touching router
tags/`responses=` (or adding `app/routers/*.py`) trips the **public-contract** category. If the
SUMMARY declares a lane below `high-risk`, the commit is **BLOCKED (exit 2)**.

The intended escape hatch — when you can *prove* the contract is safe — is to downgrade that one
category from BLOCK to WARN for the commit, not to inflate the lane to `high-risk`:

```bash
RISK_WARN_CATEGORIES="public-contract" git commit -m "..."
```

This keeps the lane honest (`normal`) while acknowledging the gate fired. Record the
justification in the commit body and in `SUMMARY.md` (e.g. "P2 proven byte-identical via
openapi diff vs baseline").

The proof that licenses the override:

```python
# capture app.openapi() BEFORE any change -> baseline.json; after the change, assert:
#  - no operation LOSES an error code   (never weaken the contract)
#  - no operation GAINS a spurious code (router-level responses= MERGE into every route,
#    so only lift a code that was already on EVERY route of the group)
```

## How to Use

1. Before editing, dump `app.openapi()` to a baseline (tags + per-op `responses` codes).
2. Make the change; re-dump and diff. Confirm byte-identical (tag/model dedup) or
   superset-or-equal (lifting shared `responses=` to the `APIRouter`).
3. Commit with `RISK_WARN_CATEGORIES="public-contract"` and cite the diff result.
4. Keep `Lane: normal` in `SUMMARY.md` — do **not** self-escalate to high-risk; the override,
   not a lane bump, is the sanctioned path for a proven-safe contract touch.

## Gotchas

- **Classifier vs hook disagree on whether public-contract is a *forcing* hard gate.**
  `feature-intake/SKILL.md` Step-3 hard-gate list **omits** "public contract" (so it does not
  force `high-risk`), but `rules/orchestration.md` ESCALATE list **and** the auto-memory
  `public-contract-hard-gate` **include** it. Net effect today: classify as `normal` per
  feature-intake, then expect the hook to fire and authorize warn-only. This drift is filed as a
  ratchet candidate in `docs/harness-experimental/improvement-backlog.md` — reconcile the two
  lists so the classifier and the hook agree.
- The memory `public-contract-hard-gate` frames the block around **new endpoints**; in practice
  the hook also fires for *modifying* existing routes' `responses=`/`tags=`. Modifying error
  docs is lower-risk than adding a public callable, but the same override clears both.
- FastAPI auto-generates a `422` (`HTTPValidationError`) for routes with validatable params.
  Lifting `422` to the `APIRouter` replaces that stale default with the project's
  `ErrorResponse` envelope on those routes — a doc-correctness improvement (it matches runtime),
  but it *is* an OpenAPI body-schema change. The error-code *set* is unchanged; flag the model
  normalization explicitly rather than calling it a pure no-op.

## Related

- docs/solutions/harness/commit-gate-bare-python.md
- docs/solutions/harness/formatter-strips-unused-import.md
