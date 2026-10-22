# llm-call-timeout — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: intent-review
- date: 2026-09-26
- trigger: ambiguous-direction
- question: Should the two deep-research models keep a longer timeout (600s, equal to `research_timeout_s`) instead of the global 120s, even though the approved scope was "one global timeout"?
- context: Correctness review scored 75 on this: the research graph has no LLM_RETRY, so a single idle provider call longer than 120s would fail the whole research run. Commit 85c34bbc fixed it with a code-level override. It adds an optional `timeout=` to `get_agent_llm`/`get_llm` and uses it for `trip_research` and `trip_research_grader`. Intent review flags this as drift from the scope "Thêm `timeout=` cho LLM. Mức tiny." ("add `timeout=` to the LLM; tiny lane"), plus a new public keyword argument (excess). It is not the agent_config per-node timeout that was listed as a non-goal.
- options:
  - A) Keep the override (recommended). Chat gets 120s with retry; research stays bounded by its run budget, as before. Cost: one extra optional keyword argument.
  - B) Remove the override. Research also gets 120s, and one slow research call now fails the run.
  - C) Remove the override and leave research unbounded, as it was before this change (for example with an explicit `timeout=None`). This needs the same keyword argument anyway, so it is strictly worse than A.
- default_if_no_response: BLOCK
- decision: A. Keep the research run-budget timeout override and the optional `timeout=` keyword argument on get_agent_llm/get_llm.
- decided_by: Minh Tran (owner)
- decided_at: 2026-09-26
