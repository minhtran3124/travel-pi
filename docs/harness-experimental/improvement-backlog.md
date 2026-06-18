# Improvement Backlog

Proposed mechanical guardrails mined from `/compound` failure tracks. Each row is a ratchet
candidate: a hook/test/lint/rule to build so a known mistake cannot recur. Triage and check off.

| Date | From failure (slug) | Proposed guardrail | Target path | Status |
|---|---|---|---|---|
| 2026-06-18 | formatter-strips-unused-import | Make unused-import auto-strip non-destructive mid-edit: skip F401 removal in the PostToolUse step (defer it to the commit gate), or only strip imports at commit time | `.claude/hooks/` (PostToolUse ruff/autoflake step) | open |
| 2026-06-18 | commit-gate-bare-python | Resolve the python interpreter once (`python3`/`.venv/bin/python`) instead of bare `python` in the pytest re-run | `.claude/hooks/commit-quality-gate.sh` | open |
