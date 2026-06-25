# Improvement Backlog

Proposed mechanical guardrails mined from `/compound` failure tracks. Each row is a ratchet
candidate: a hook/test/lint/rule to build so a known mistake cannot recur. Triage and check off.

| Date | From failure (slug) | Proposed guardrail | Target path | Status |
|---|---|---|---|---|
| 2026-06-18 | formatter-strips-unused-import | Make unused-import auto-strip non-destructive mid-edit: skip F401 removal in the PostToolUse step (defer it to the commit gate), or only strip imports at commit time | `.claude/hooks/` (PostToolUse ruff/autoflake step) | open |
| 2026-06-18 | commit-gate-bare-python | Resolve the python interpreter once (`python3`/`.venv/bin/python`) instead of bare `python` in the pytest re-run | `.claude/hooks/commit-quality-gate.sh` | open |
| 2026-06-23 | untracked-py-gate-root-claude | Anchor the `.claude/` exclusion to the path start: `grep -vE '(^\|/)\.claude/'` so root-level harness `.py` no longer trips the untracked-py gate | `.claude/hooks/check-untracked-py.sh` | open |
| 2026-06-23 | public-contract-gate-warn-only | Reconcile the public-contract hard-gate lists: feature-intake Step-3 omits it while orchestration.md ESCALATE + memory include it — make the classifier and `risk-corroboration.sh` agree | `.claude/skills/feature-intake/SKILL.md`, `.claude/rules/orchestration.md` | open |
