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

Restored a pre-model PII guardrail for the travel agent. Email addresses are replaced with `[REDACTED_EMAIL]` and credit-card numbers are masked to `****-****-****-<last4>` before any LLM call, checkpointer write, or memory extraction. The guardrail is implemented as a LangGraph node (`app.agents.guardrails.pii_guardrail_node`) wired as the first graph node (`START -> pii_guardrail -> load_context`). Defense-in-depth redaction is also applied in `app.routers.agent` before the user turn is persisted to the `messages` table or passed to the graph, covering both `/agent/chat` and `/agent/stream`. Names and phone numbers are intentionally left untouched so MIN-53 personalization and booking tools continue to work.

### Rationale

The project uses LangGraph `StateGraph`, not LangChain `create_agent`, so the official `PIIMiddleware` cannot be plugged in directly. A LangGraph-native entry node is the idiomatic equivalent of middleware and guarantees the model never sees raw email/card input. Router-boundary redaction was added because the conversation store persists the user turn before the graph runs, so the graph node alone would leave raw PII in the DB.

### Alternatives considered

- Use LangChain `PIIMiddleware` directly — rejected because it requires `create_agent` and this project compiles a `StateGraph`.
- Reuse `langchain.agents.middleware._redaction.detect_credit_card` — rejected because it only matches 16-digit patterns and misses 15-digit Amex / 14-digit Diners; the restored custom Luhn-window detector handles 13–19 digits and glued expiry cases.
- Redact names/phone too — rejected to avoid breaking MIN-53 personalization and booking contact capture.

### Deviations

- none

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Guardrail unit tests | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/agents/test_pii_redaction.py -x` | 0 | 17 passed |
| Graph + guardrail tests | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/agents/test_graph.py tests/agents/test_pii_redaction.py -x` | 0 | 20 passed |
| Router persistence test | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/api/agent/test_agent_chat.py -x -k pii` | 0 | 1 passed |
| Regression sweep | `cd apps/api && /Users/minhtran/Documents/minhtran3124/developer/travel-pi/.venv/bin/python -m pytest tests/agents tests/api/agent tests/memory -q` | 0 | 421 passed, 1 warning |

### Rollback

- `git revert 343cbcc` (or the merge commit if squashed)

### Advisory Findings

From the final 6-angle correctness review (HEAD `cd395625`). All scored below the 75 threshold and do not block shipping; they are documented here for future scope decisions.

1. **Internationalized email addresses bypass `_EMAIL_RE`** (`guardrails.py:28`) — Unicode local parts (e.g. `minh.trần@example.com`) and IDN domains are not matched by the ASCII-centric regex. Score: 50. Out of the confirmed MIN-62 scope; fixing it requires a deliberate expansion of PII detector coverage.
2. **Credit-card separators are limited** (`guardrails.py:34`) — Only spaces, dots, hyphens, and newlines are tolerated. Cards grouped with commas, slashes, or parentheses are not masked. Score: 50. Same scope decision as above.
3. **`pii_guardrail_node` no-ops when `HumanMessage.id` is `None`** (`guardrails.py:131`) — This is intentional: without an id, `add_messages` would append a duplicate message instead of replacing in place. The normal graph path always assigns an id before this node runs; direct callers without an id are a defense-in-depth gap, not the primary path. Score: 25.
4. **Email glued to a trailing word character bypasses redaction** (`guardrails.py:28`) — `\b` word boundaries mean `foo@bar.com1` or `foo@bar.com_suffix` are not matched. Score: 25. Standard regex limitation; real users typically separate emails with whitespace or punctuation.

### Harness-Delta

- Added `.worktrees/` to `.gitignore` (commit `b4c70e6`) to support isolated feature-branch worktrees.
