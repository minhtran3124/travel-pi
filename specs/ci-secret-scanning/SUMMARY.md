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

New `secrets` job in `.github/workflows/ci.yml`. It installs gitleaks 8.30.1 as a pinned, sha256-verified binary (no third-party action, `contents: read` only) and scans the PR's own commits (`base.sha..head.sha`). New `.gitleaks.toml` extends the default rules with 3 allowlists. Each matches the extracted *secret* only, never a whole line or path, and each covers a false positive verified on the one-off full-history scan: 1,352 commits, 15 findings, 0 real credentials.

### Rationale

Cheapest control from the 2026-09-15 threat-intel review: the report documents actors mining GitHub, Docker images and APKs for hardcoded keys, and this repo has no scanning (`grep -rniE "gitleaks|trufflehog|detect-secrets" .github .pre-commit-config.yaml .husky package.json` → 0).

### Alternatives considered

- `gitleaks/gitleaks-action`: less YAML, but a third-party action gets `GITHUB_TOKEN`. Rejected by default.
- trufflehog: verifies live credentials over the network, which is heavier and makes outbound calls from CI. gitleaks is enough for a repo this size.
- Pre-commit hook: catches leaks earlier, but needs a new local toolchain dependency. Deferred.

### Deviations

- Route: no `PLAN.md` and no implementer subagent dispatch. The change is 2 files and fewer than 3 steps, below the plan threshold in `rules/orchestration.md` (Artifact policy). The controller implemented it directly; per-task independent review still runs (`task-reviewer`).

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| intake baseline: no scanner in CI today | `grep -rniE "gitleaks\|trufflehog\|detect-secrets" .github` | 1 | exit 1 = no match; confirms the gap before any change | |
| full-history scan, no config (triage) | `gitleaks git --redact .` | 1 | 1352 commits, 15 findings, all false positives: 11× `ANTHROPIC_API_KEY=` (env-neutralization lines in specs), 3× `idempotency_key=idempotency_key` (routers), 1× sample header in `APIS.md` | |
| full-history scan, with config | `gitleaks git --redact -c .gitleaks.toml .` | 0 | no leaks found (1354 commits) | |
| working-tree scan, with config | `gitleaks dir --redact -c .gitleaks.toml .` | 0 | no leaks found | |
| negative control: allowlists don't mask real keys | `gitleaks stdin -c .gitleaks.toml < control.txt` | 1 | 2 fake keys detected, including one placed after `ANTHROPIC_API_KEY=` on an env-neutralization line | |
| CI scan step, exact command form, simulated locally | `RUNNER_TEMP=<dir> BASE_SHA=$(git rev-parse HEAD~5) HEAD_SHA=$(git rev-parse HEAD) sh -c '"$RUNNER_TEMP/gitleaks" git --redact --no-banner --log-opts="${BASE_SHA}..${HEAD_SHA}" .'` | 0 | range scan works with the `$RUNNER_TEMP` path and env-passed SHAs | |
| workflow YAML parses | `ruby -ryaml -e 'YAML.load_file(".github/workflows/ci.yml")'` | 0 | jobs: secrets, api, web, web-e2e | |

### Review

- `task-reviewer`: **Spec PASS, Quality PASS**.
  - Fixed: checkout persisted `GITHUB_TOKEN` in `.git/config`, readable by the scanner. Now `persist-credentials: false`.
  - Fixed: the binary is downloaded to `$RUNNER_TEMP` instead of the checkout root.
  - Backlog: a PR can add an allowlist entry to `.gitleaks.toml` that hides its own secret. Add a CODEOWNERS entry for `.gitleaks.toml`, or have reviewers check changes to it.

### Not auto-verified

- That the CI job actually fails on a leaked secret on a real PR: reached traceability only until a PR run is observed.
- That a failing `secrets` job *blocks merge*: this depends on branch protection marking `secrets` as required. It is a repository setting and not visible from the repo.
- Merge commits: `git log -p` shows no diff for merge commits, so a secret introduced only while resolving a conflict is not scanned (reviewer note; accepted).

### Rollback

- `git revert <sha>` (CI config only; no runtime or data impact)

### Harness-Delta

- backlog: `using-git-worktrees` says to run `scripts/deploy-harness.sh` inside the worktree, but that script is not in this repo (`.claude/` is git-excluded), so a sibling worktree has no harness of its own.
- fix-direct (noted): shell is zsh, so `${PIPESTATUS[n]}` prints empty. Verify exit codes were captured with unpiped reruns.
