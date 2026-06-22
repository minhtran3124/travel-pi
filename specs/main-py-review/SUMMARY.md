# main-py-review — Summary

Lane: high-risk
Confidence: high
Reason: 4 risk flags fire (public contract, existing behavior, weak proof, access logs); no Step-3 hard gate, direction unambiguous.
Flags: public-contracts, existing-behavior, weak-proof, audit/security (access logs)
Affects: app/main.py error-envelope contract (500 response shape), `_log_requests` middleware, OpenAPI operationIds; collaborators app/core/{errors,middleware}.py (new), app/core/config.py
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

<!-- Verbatim originating request + the intake target. -->

Originating goal (verbatim): "make the deep research to review @app/main.py for best practice, now it contains a lot of config, but dont have some important like middleware, etc ..."

Intake target (verbatim): "for specs/main-py-review/REVIEW.md" — classify and route the work of implementing the findings in `specs/main-py-review/REVIEW.md`.

## What changed

Implemented REVIEW.md P1–P6 on branch `feat/main-py-review` (5 atomic commits).
**P1** (`d5170a1`): unhandled exceptions now return the JSON error envelope
(`error="InternalServerError"`, prod hides detail) and are access-logged — verified
broken before. **P2** (`b866eec`): handlers extracted to `app/core/errors.py`,
middleware to `app/core/middleware.py`; `create_app` is now a 58-line orchestrator.
**P4** (`b866eec`): request logging split from rate-limit headers. **P3** (`9212c81`):
GZip (>1KB) + an `X-Request-ID` generated/echoed per request, surfaced in the access
log and error envelopes. **P6** (`9b78f8e`): `Settings` rejects wildcard CORS +
credentials in production. **P5** (`bb16b61`): startup fails on duplicate
schema-visible operationIds.

### Rationale

High-risk by flag count, not by a hard gate. The one correctness bug (P1) is verified
against installed `starlette 1.2.1` + a live `TestClient` probe; the rest are
structure/observability. Lane is high-risk because the change is client-visible (500
envelope + operationIds), alters test-covered behavior, and the affected 500 path
currently lacks proof — so it demands a PLAN + per-task review, not a human gate.

### Alternatives considered

- **Slice P1 only as a `normal`-lane bugfix** (public-contract + existing-behavior +
  weak-proof = 3 flags → normal) and defer P2–P6. Viable faster path if the user wants
  the bug fixed before the refactor. Recommended split if scope is trimmed.
- Treat the whole review as `normal` — rejected: 4 flags crosses the high-risk threshold.

### Deviations

- Rule 1 (Task 2.1) — the plan's caplog test didn't survive `create_app()`'s `dictConfig` replacing root handlers; re-attached `caplog.handler` after the call. Commit `d5170a1`.
- Rule 1 (Task 3.2) — two pre-existing prod-`Settings` tests (`test_meta.py`, `test_errors.py`) constructed the now-invalid wildcard-CORS-with-credentials prod config; updated them to pass an explicit origin. Orchestrator-authorized scope widening of Task 3.2 `<files>`. Commit `9b78f8e`.
- Rule 1 (Task 3.3) — the plan's verbatim operationId guard omitted the `include_in_schema` filter and crashed startup on the pre-existing intentional `dashboard_index` double-decorator; added the filter to mirror the existing test-time invariant. Commit `bb16b61`.

### Verify

<!-- Filled by the implementing waves. Intake ran no code-changing checks. -->

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Reproduce P1 (pre-fix: plaintext 500) | `TestClient(app, raise_server_exceptions=False).get('/__boom')` | 0 | At intake: status 500, content-type text/plain, no X-RateLimit, no access-log line |
| Lint | `ruff check app tests` | 0 | All checks passed (pre-existing test_logging.py reformat left untouched) |
| Full suite | `python -m pytest -q` | 0 | **692 passed** (682 baseline + 10 new tests) |
| Infra suite | `python -m pytest tests/infra -q` | 0 | 39 passed (errors envelope incl. 500, middleware gzip/request-id, cors, operation_ids) |

### Rollback

- Revert code: `git revert <sha>` (no migrations; all changes are app-code).

### Harness-Delta

- backlog — the corroboration hook may block the commit: changing the 500 response
  shape is a public-contract change. Per memory `public-contract-hard-gate`, authorize
  with `RISK_WARN_CATEGORIES="public-contract"` if `risk-corroboration.sh` blocks.
