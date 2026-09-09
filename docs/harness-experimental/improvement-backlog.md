# Improvement Backlog

Proposed mechanical guardrails mined from `/compound` failure tracks. Each row is a ratchet
candidate: a hook/test/lint/rule to build so a known mistake cannot recur. Triage and check off.

| Date | From failure (slug) | Proposed guardrail | Target path | Status |
|---|---|---|---|---|
| 2026-06-18 | formatter-strips-unused-import | Make unused-import auto-strip non-destructive mid-edit: skip F401 removal in the PostToolUse step (defer it to the commit gate), or only strip imports at commit time | `.claude/hooks/` (PostToolUse ruff/autoflake step) | open |
| 2026-06-18 | commit-gate-bare-python | Resolve the python interpreter once (`python3`/`.venv/bin/python`) instead of bare `python` in the pytest re-run | `.claude/hooks/commit-quality-gate.sh` | open |
| 2026-06-23 | untracked-py-gate-root-claude | Anchor the `.claude/` exclusion to the path start: `grep -vE '(^\|/)\.claude/'` so root-level harness `.py` no longer trips the untracked-py gate | `.claude/hooks/check-untracked-py.sh` | open |
| 2026-06-23 | public-contract-gate-warn-only | Reconcile the public-contract hard-gate lists: feature-intake Step-3 omits it while orchestration.md ESCALATE + memory include it — make the classifier and `risk-corroboration.sh` agree | `.claude/skills/feature-intake/SKILL.md`, `.claude/rules/orchestration.md` | open |
| 2026-06-26 | wave-shared-file-partition | Compare each wave subagent's actually-touched files (git diff) against its task `<files>` and flag edits outside the declared set; complement with a planning lint requiring any file/type imported by ≥2 same-wave tasks to be produced in a prior non-parallel wave | `.claude/hooks/blast-radius-check.sh` | open |
| 2026-07-08 | supervisor-active-yaml-is-a-pointer | Warn when a diff modifies `app/prompts/*/active.yaml` beyond its version-pointer keys (prose belongs in the active `vN.md`) | `.claude/hooks/` (PreToolUse/commit gate) | open |
| 2026-07-08 | sse-additive-field-breaks-cross-dir-shape-test | A task editing a shared event/DTO factory must list every `== {...}` shape-assertion test for that payload in `<files>` and run those dirs in `<verify>` — cross-dir contract tests escape a module-local verify | `.claude/hooks/blast-radius-check.sh` (+ plan lint) | open |
| 2026-07-11 | verify-against-invented-rule | Flag a test module that defines a single module-level `TODAY`/`NOW` constant and tests functions taking it as a parameter, with no `parametrize` over multiple anchors — anchor-dependent behavior tested from one anchor should justify itself | `.claude/hooks/` (test lint) | open |
| 2026-07-11 | negative-grep-is-not-absence | A test that greps every ACTIVE prompt (resolved via `active.yaml`, not the directory) for a feature's declared list of retired phrases — so a rule deleted from one prompt but alive in another is a red test, not a lucky runtime | `apps/api/tests/prompts/` | open |
| 2026-09-09 | commit-gate-audits-main-checkout-index | Invert the REPO_DIR precedence: prefer `git rev-parse --show-toplevel` (the repo the commit runs in) and fall back to `CLAUDE_PROJECT_DIR` only when unavailable, so a linked worktree's commit is audited against its own index | `.claude/hooks/commit-quality-gate.sh` | open |
