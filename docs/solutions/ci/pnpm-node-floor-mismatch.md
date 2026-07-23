---
problem_type: bug
module: ci
tags: ci, pnpm, node-version, github-actions, packagemanager
severity: critical
applicable_when: CI fails in setup-node with ERR_UNKNOWN_BUILTIN_MODULE node:sqlite, or when bumping/pinning the packageManager pnpm version.
affects:
  - .github/workflows/ci.yml
  - package.json
supersedes: null
confidence: high
confirmed_at: 2026-06-26
---
## Problem

The CI `web` job died in the `actions/setup-node` pnpm-cache step with a cryptic error:

```
Error [ERR_UNKNOWN_BUILTIN_MODULE]: No such built-in module: node:sqlite
warn: This version of pnpm requires at least Node.js v22.13
```

Nothing in the repo references `node:sqlite`, and local `pnpm install` worked fine — so the failure looked like a corrupt environment, unrelated to the change.

## Root Cause

Two version pins disagreed about the Node floor:
- `package.json` pinned `"packageManager": "pnpm@11.9.0"`, and pnpm 11's internals `import "node:sqlite"` — a builtin that exists only on **Node ≥ 22.13**.
- `.github/workflows/ci.yml` set `node-version: "20"`.

`actions/setup-node` honors the `packageManager` pin and shells out to pnpm 11 **under Node 20** to prime its cache → the builtin is missing → crash. The error names the missing module, not the version mismatch, which is what makes it cryptic.

## Fix

- `.github/workflows/ci.yml`: `node-version: "24"` (≥ pnpm's 22.13 floor; matches local dev).
- `package.json`: `engines.node: ">=22.13"` to make the floor explicit and fail fast locally too.

## Regression Test

[none] — CI config; the CI run itself is the guard. `engines.node` surfaces the floor locally on install.

## Code Example

```yaml
# .github/workflows/ci.yml
- uses: actions/setup-node@v4
  with:
    node-version: "24"   # was "20" — pnpm@11 needs Node >=22.13 (node:sqlite)
    cache: pnpm
```

## Prevention

Treat **three pins as one coupled triple**: `packageManager` (pnpm/npm/yarn version), CI `node-version`, and `engines.node`. When you bump or pin the package manager, raise CI `node-version` and `engines.node` to its runtime floor **in the same change**. A `node:<builtin>`-not-found error during dependency install almost always means "the package manager is running on too-old a Node," not a real missing module.

## Related
- docs/solutions/monorepo/operate-from-subdir.md
