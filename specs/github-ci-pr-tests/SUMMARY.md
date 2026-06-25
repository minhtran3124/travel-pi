# github-ci-pr-tests — Summary

Lane: normal
Confidence: high
Reason: Touches one external system (GitHub Actions CI); no hard gates fire; direction is unambiguous.
Flags: external-systems
Affects: .github/workflows/ (new CI infrastructure)
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

setup github action for each PR need to run all unittest and make sure all passed. if not, dont allow merge PR

## What changed

_to be filled after implementation_

### Rationale

_to be filled after implementation_

### Alternatives considered

- none

### Deviations

- none

### Verify

| Check | Command | Exit | Notes |
|-------|---------|------|-------|
| _to be filled_ | | | |

### Rollback

- Remove `.github/workflows/ci.yml`: `git rm .github/workflows/ci.yml && git commit -m "revert: remove CI workflow"`
- Branch protection rules must be manually reverted in GitHub repo settings
