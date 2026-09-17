# ci-secret-scanning — Summary

Lane: normal
Confidence: medium
Reason: CI-only security tooling (no secret is read, stored or handled, so the audit/security hard gate does not apply); 3 non-gate flags fired — security-adjacent, external tool in CI, new failing check on existing PR flow
Flags: audit/security-adjacent, external-systems, existing-behavior
Affects: .github/workflows/ci.yml (CI pipeline for every PR); optional new .gitleaks.toml
Input-type: change request
Route: using-git-worktrees → subagent-driven-development (PLAN.md light: ≤3 tasks)
Escalate: no — but a real secret found in history escalates (rotation is an external action owned by the user)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

User request (2026-09-15), verbatim:

> /feature-intake cho section "Không secret scanning"

The section it references, from `docs/reviews/2026-09-15-threat-intel-review.md` §3 (TI-3), verbatim:

> **Đề xuất:** thêm job gitleaks vào `ci.yml` (rẻ, rủi ro thấp). Quét cả lịch sử một lần.

### Classification notes

- **Hard gates checked** against `.claude/harness-manifest.json`:
  - `audit/security` ("sensitive/secret handling"): not hit. The change adds a scanner that *detects* secrets and handles none. The hook regex (`risk-corroboration.sh:175`: `audit_log|access_log|encrypt|decrypt|pii|sensitive_data`) would not fire on a workflow diff either.
  - `external-provider`: not hit. No dependency manifest changes (`risk-corroboration.sh:169`).
  - `high-blast`: not hit. `.github/workflows/*` is not on the list (settings.json, hooks, render_plan.py).
- **Ambiguities, resolved with documented defaults (→ Confidence medium):**
  1. Scope. Reading A: CI job only. Reading B: CI job + local pre-commit hook. **Default: A**, matching the review text ("thêm job gitleaks vào `ci.yml`"). Pre-commit stays out of scope, since the repo has no pre-commit framework today and adding one is a separate decision.
  2. "Quét cả lịch sử một lần": **default** is one local `gitleaks git` run over full history as a Verify row, not a recurring CI job. The PR job scans only the PR's commit range, so it stays fast.
  3. Tooling. Options are the `gitleaks/gitleaks-action` action or a pinned gitleaks binary. **Default: pinned binary** (versioned download + checksum). This avoids a third-party action holding `GITHUB_TOKEN`, which is itself the supply-chain risk the threat report warns about.
  4. False positives (`.env.example`, test fixtures such as the dummy Supabase keys): handled by a minimal `.gitleaks.toml` allowlist with a reason per entry. Never by blanket path exclusions.
- **Escalation trigger:** if the history scan finds a *real* credential, stop and write `ESCALATIONS.md`. Rotating the key and deciding on a history rewrite belong to the user, and a force-push is never done autonomously.

## What changed

_(pending — intake only)_

### Rationale

Cheapest control from the 2026-09-15 threat-intel review: the report documents actors mining GitHub, Docker images and APKs for hardcoded keys, and this repo has no scanning (`grep -rniE "gitleaks|trufflehog|detect-secrets" .github .pre-commit-config.yaml .husky package.json` → 0).

### Alternatives considered

- `gitleaks/gitleaks-action`: less YAML, but a third-party action gets `GITHUB_TOKEN`. Rejected by default.
- trufflehog: verifies live credentials over the network, which is heavier and makes outbound calls from CI. gitleaks is enough for a repo this size.
- Pre-commit hook: catches leaks earlier, but needs a new local toolchain dependency. Deferred.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| intake baseline: no scanner in CI today | `grep -rniE "gitleaks\|trufflehog\|detect-secrets" .github` | 1 | exit 1 = no match; confirms the gap before any change | |

### Not auto-verified

- That the CI job actually blocks a leaked secret on a real PR: reached traceability only until a PR run is observed.

### Rollback

- `git revert <sha>` (CI config only; no runtime or data impact)

### Harness-Delta

- none
