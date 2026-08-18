<!--
  Canonical SUMMARY.md shape. Copy to specs/<slug>/SUMMARY.md at intake.

  The header block is machine-read:
    - hooks/risk-corroboration.sh greps the `Lane:` line to corroborate it
      against the staged diff (a hard-gate signal in the diff + a Lane below
      high-risk = blocked).
    - the trust-metrics ledger reads Lane / Confidence / Flags per task.
  Keep the five header fields present and on their own lines. Do not delete them.
-->

# pii-middleware-guardrail — Summary

Lane: high-risk
Confidence: high
Reason: Audit/security hard gate (PII redaction) + touches agent graph + external LLM provider + existing agent behavior.
Flags: audit/security, external-systems, existing-behavior, multi-domain
Affects: app.agents (graph, state, prompts), app.routers.agent, app.memory
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> review codebase hiện tại và lên plan để bring back PII trở lại, make sure là làm đúng ở lớp middleware (tức là model sẽ ko thấy info này), chỉ có code chạy thôi. Research thêm best practice ở offical document.

## What changed

TBD — this is the intake/planning artifact for bringing back PII redaction as a middleware/guardrail layer so that sensitive user input is redacted before it reaches the LLM model. The scope is code-only: design the guardrail, wire it into the agent invocation path, and verify with tests.

### Rationale

TBD — to be filled after research and planning.

### Alternatives considered

- TBD

### Deviations

- none

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| TBD | TBD | - | - |

### Rollback

- `git revert <sha>`

### Harness-Delta

- none
