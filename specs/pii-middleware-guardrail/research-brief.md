# PII Middleware Guardrail — Research Brief

## 1. What is the repo really?

- Python 3.12+ FastAPI backend in `apps/api/`
- LangGraph 1.x + LangChain 1.3.11 (confirmed in `.venv`)
- Agent is a `StateGraph` compiled in `apps/api/app/agents/graph.py`, NOT using LangChain `create_agent`
- Conversation state persisted via LangGraph checkpointer + `conversations`/`messages` SQL tables

## 2. What already exists locally?

- `apps/api/app/tools/_base.py`: redacts `preferences` from tool logs (`_REDACTED_PARAM_KEYS`).
- `apps/api/app/tools/flight_tools.py` / `hotel_tools.py`: explicit non-PII logging for bookings.
- Tests: `tests/tools/test_preference_ranking.py`, `tests/tools/test_booking_tools.py` verify PII stays out of logs.
- Previous implementation existed in branch `feat/min-62-pii-guardrail` (commits `a153706`, `7cacf1a`, merge `02c5f20`) but is **not an ancestor of current HEAD**.
  - Files: `apps/api/app/agents/guardrails.py`, `apps/api/tests/agents/test_pii_redaction.py`
  - Wiring: `START -> pii_guardrail -> load_context` in `graph.py`
  - Router boundary redaction in `_turn_input`
- Current `apps/api/app/agents/graph.py` has no guardrail node.

## 3. Ecosystem / upstream patterns

- LangChain 1.3.11 provides `langchain.agents.middleware.PIIMiddleware`, but it is designed for `create_agent`, not `StateGraph`.
- LangGraph does not have a native "middleware" abstraction; the idiomatic pattern is a pre-processing graph node that mutates state before model nodes.
- Upstream PII detectors in `langchain.agents.middleware._redaction`:
  - `detect_email`: standard regex
  - `detect_credit_card`: only matches 16-digit patterns (verified: misses 15-digit Amex and 14-digit Diners)
  - strategies: `block`, `redact`, `mask`, `hash`

## 4. Official docs / version-matched recommendations

- `PIIMiddleware` docstring recommends applying redaction to input (`apply_to_input=True`) before model calls.
- Strategy guidance from docstring:
  - `redact`: general compliance, log sanitization
  - `mask`: human readability
  - `hash`: pseudonymous analytics/debugging
  - `block`: avoid PII completely
- Best practice: detect and handle PII **before** it reaches the model, checkpointer, or memory extractor.

## 5. Lightest credible path

Because the project uses LangGraph `StateGraph`, we cannot plug in `PIIMiddleware` directly. The recommended path is:

1. **Restore a LangGraph-native guardrail node** (`apps/api/app/agents/guardrails.py`) that runs as the first node in the graph.
2. **Reuse the proven custom redaction logic** from commit `7cacf1a` rather than LangChain's narrower built-in detectors:
   - Email → `[REDACTED_EMAIL]`
   - Credit card (13–19 digits, Luhn window search) → `****-****-****-<last4>`
3. **Wire it in `graph.py`** as `START -> pii_guardrail -> load_context`, so all model-bound messages are redacted before any LLM call and before checkpointer/memory extraction.
4. **Keep router boundary redaction** in `_turn_input` as defense-in-depth for the REST/SSE entry points.
5. **Scope remains narrow**: email + credit card only, names/phones untouched (to avoid breaking MIN-53 personalization).
6. **Tests**: restore and extend `tests/agents/test_pii_redaction.py` with regression cases from the old branch.

This is the minimum diff that satisfies "middleware layer" (pre-model graph node) and "model never sees PII" while staying idiomatic to the current LangGraph architecture.
