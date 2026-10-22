# llm-pricing-coverage — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: intent-review
- date: 2026-09-25
- trigger: ambiguous-direction
- question: For proposal 5 ("Báo lỗi rõ khi model trong cấu hình chưa có trong pricing.py"), is a server-log WARNING enough, or should the config dashboard show a warning when an admin saves an unpriced model?
- context: Today the warning only reaches the backend log (`reload_from_db`, `estimate_cost`). The dashboard save flow (`routers/dashboard.py` `agent_config_save`) still shows only the plain "saved" banner. Nothing is rejected, so the "warn, not reject" default holds either way.
- options:
  - A) Keep it log-only. Ship as is, and record the gap as advisory drift.
  - B) Also show a non-blocking warning banner on the dashboard after saving an unpriced model. The save still succeeds. This adds roughly one router check, one template line and a test.
- default_if_no_response: BLOCK
- decision: B. After a successful save, show a non-blocking warning banner on the dashboard when the saved model is unpriced. The save still succeeds.
- decided_by: Minh Tran (owner)
- decided_at: 2026-09-25
