# ci-actions-node24 — Summary

Lane: normal
Confidence: high
Reason: 3 workflow files (above the one-file tiny limit); 2 non-gate flags (external third-party actions change version, existing CI behavior); no manifest hard gate (.github/workflows is not high-blast; no dependency manifest touched)
Flags: external-systems, existing-behavior
Affects: .github/workflows/ci.yml, eval.yml, state-on-merge.yml
Input-type: maintenance
Route: worktree → direct patch (below the plan threshold) → independent task review → PR
Escalate: no

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

User request (2026-09-15), in chronological order, verbatim:

> warning post run action cua action secrets

> ok, lam PR do di

The "PR đó" (that PR) the user approved, as proposed by the assistant:

> nâng tất cả action trong `.github/workflows/*` lên bản chạy Node 24 [...] Trước khi nâng, tôi sẽ kiểm tra bản mới nhất của từng action qua release trên GitHub.

## What changed

Every action in `.github/workflows/*` moves to the **first major that declares `runs.using: node24`**, not the latest. The goal is to drop Node 20, and the first Node-24 major carries the fewest unrelated breaking changes. Runtime was read from each tag's `action.yml`; breaking changes from each intermediate major's `.0.0` release notes.

| Action | Was | Now | Latest | Breaking changes vs. how this repo uses it |
| --- | --- | --- | --- | --- |
| `actions/checkout` | v4 | v5 | v7.0.1 | runtime only (runner ≥ 2.327.1; hosted runners qualify) |
| `actions/setup-python` | v5 | v6 | v7.0.0 | runtime only |
| `actions/setup-node` | v4 | v5 | v7.0.0 | auto-cache when `packageManager` is set. No effect: `cache: pnpm` is already explicit |
| `actions/upload-artifact` | v4 | v6 | v7.0.1 | runtime only (v5 still ran Node 20) |
| `pnpm/action-setup` | v4 | v5 | v6.1.0 | runtime only |
| `astral-sh/setup-uv` | v4 | v7 | v10.1.0 | v5: `enable-cache` defaults to true on hosted runners, and `requirements*.txt` is in the default cache glob, so jobs now **gain a uv cache save/restore step**. v6: venv auto-activation only with `python-version` (not passed here). v7: `server-url` removed (not used). v5–v6 still ran Node 20; v8+ publish no floating `vN` tag |

16 lines changed across `ci.yml`, `eval.yml` and `state-on-merge.yml`. No `with:` inputs changed.

### Rationale

GitHub runners are deprecating Node 20. Every Node-20 JavaScript action now prints a deprecation warning and runs on Node 24 anyway. Bumping to majors that declare `node24` removes the warning before Node 20 is removed for good.

### Alternatives considered

- Set `ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION`: this only postpones the problem and keeps an unsupported runtime. Rejected.
- Bump only the `secrets` job (PR #210): the other jobs would keep warning. Rejected.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| target majors declare node24 | `gh api "repos/<owner>/<action>/contents/action.yml?ref=<major>" --jq .content \| base64 -d \| grep -A1 '^runs:'` | 0 | checkout v5, setup-python v6, setup-node v5, upload-artifact v6, pnpm v5, setup-uv v7 are all `node24`. upload-artifact v5 and setup-uv v5/v6 are still `node20`, so those majors were skipped | |
| workflow YAML parses | `ruby -ryaml -e 'Dir[".github/workflows/*.yml"].each{\|f\| YAML.load_file(f)}'` | 0 | ci.yml (api, web, web-e2e), eval.yml (eval-smoke), state-on-merge.yml (mark-shipped) | |
| no Node-20 major left | `git grep -nE "actions/checkout@v4\|setup-python@v5\|setup-node@v4\|upload-artifact@v[45]\b\|pnpm/action-setup@v4\|setup-uv@v[4-6]\b" -- .github/workflows` | 1 | exit 1 = no match | |

### Review

- `task-reviewer`: **Spec PASS, Quality PASS**.
  - All 16 `uses:` lines match the table, and no other workflow or composite action exists.
  - `cache: pnpm` is explicit, so setup-node v5 auto-caching does not apply.
  - pnpm still resolves from `packageManager`.
  - state-on-merge's checkout still persists the token its `git push` needs.
  - pnpm/action-setup still runs before setup-node.
- The reviewer's one finding ("Verify table empty") is stale: the reviewer read SUMMARY before the Verify rows were added, and `verify_summary.py --lane` passed afterwards. Its `actionlint` suggestion was not taken: the tool is not installed, and this PR's own CI run is the stronger check (see below).

### Not auto-verified

- That the Node-20 deprecation warning is gone and all jobs still pass: reached traceability only. Needs this PR's own CI run (api, web, web-e2e). `eval-smoke` and `mark-shipped` do not run on this PR's triggers.
- PR #210 (`ci-secret-scanning`, open) adds a `secrets` job with `actions/checkout@v4`. Whichever PR merges second must bump that line to `@v5`, or the warning returns for that job.

### Rollback

- `git revert <sha>` (CI config only)

### Harness-Delta

- none
