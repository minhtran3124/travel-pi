# readme-agent-human-guide — Summary

Lane: normal
Confidence: high
Reason: Documentation-only change across the root README and its required planning record; no runtime, dependency, or public-contract change.
Flags: none
Affects: repository onboarding documentation
Input-type: maintenance

### Intent

review and update README.md with best practice now. useful with AI agent coding and human reading

## What changed

Rewrote the root README as the project entry point for people and coding agents. It now explains the product boundary, maps the web/API/agent architecture, provides verified setup and everyday commands, and routes readers to the authoritative documentation for each task.

### Rationale

The README now presents the information needed to get productive before implementation details, while linking rather than duplicating detailed backend and agent documentation. Commands and configuration guidance were derived from the committed Makefiles, manifests, and environment examples.

### Alternatives considered

- Expand every app-level README in the same pass — not chosen because the request targets the root README and the existing detailed sources should remain the source of truth.

### Deviations

- Rule 3 — Replaced the stale `verify_summary.py --lint` invocation suggested by the planning rule with the script’s supported `readme-agent-human-guide --check` form in `specs/readme-agent-human-guide/PLAN.md`.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| Plan contract | `python3 .claude/scripts/check_plan_contract.py specs/readme-agent-human-guide/PLAN.md` | 0 | Plan contract passed. | SC-3 |
| Product-boundary section | `rg -q "## Product boundaries" README.md` | 0 | Required section present. | SC-1 |
| Contributor-workflow section | `rg -q "## Working with the codebase" README.md` | 0 | Required section present. | SC-2 |
| Internal Markdown links | `python3 -c 'from pathlib import Path; import re; text = Path("README.md").read_text(); links = re.findall(r"\\]\\(([^)]+)\\)", text); missing = [link for link in links if not link.startswith(("http://", "https://", "#")) and not Path(link).exists()]; assert not missing, missing; print(f"validated {len(links)} Markdown links")'` | 0 | Validated 17 Markdown links. | SC-2 |
| Documented Make targets | `make -n api web dev test test-docker lint build seed up down` | 0 | All documented root Make targets expand successfully. | SC-2 |
| Scoped whitespace check | `git diff --check -- README.md specs/readme-agent-human-guide/PLAN.md specs/readme-agent-human-guide/SUMMARY.md` | 0 | No whitespace errors in this change. | SC-1 |

### Not auto-verified

- Local startup, Docker startup, authentication, and live LLM replies — reached traceability; commands/configuration were checked against committed build files and examples but services were not started for this documentation-only change.

### Rollback

- `git revert <commit-sha>`

### Harness-Delta

- none
