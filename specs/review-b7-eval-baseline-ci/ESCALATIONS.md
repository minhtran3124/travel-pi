# review-b7-eval-baseline-ci — Escalations

Default: **deny-on-no-response**. No recorded decision → work stays blocked.
(Enforced: `hooks/commit-quality-gate.sh` denies commits touching this slug while any `decision:` is `pending`.)

---

## E001

- raised_by: orchestrator (feature-intake)
- date: 2026-09-07
- trigger: ambiguous-direction
- question: What happens to `feat/agent-eval-pipeline` (evalkit) — merge it, close it, or salvage pieces onto the MIN-58 harness?
- context: The review says "merge hoặc đóng evalkit". The branch is 8 commits, forked 07-13, 335 commits behind `main`, and `git merge-tree` reports conflicts in 15+ files including modify/delete on the six legacy `eval/` modules it retires (main kept editing them). It touches no `apps/api/app/**`. Every other task in this spec (baseline format, CI workflow, make targets) depends on which harness survives.
- options:
  - A) **Merge evalkit** — rebase/resolve the 15-file conflict set, retire `eval/{harness,loader,metrics,metrics_geval,run_deepeval,run_eval}.py` + their tests (Rule-4 remove-functionality), inherit `eval.yml`, `make eval-*`, 84 goldens, Report/baseline gate. Biggest payoff, biggest diff; the branch's own SUMMARY notes its PR job is `--dry-run` only, so the keyless gate still needs work after merge.
  - B) **Close evalkit** — keep the MIN-58 `eval/` harness that `main` has been evolving; add a committed baseline + regression compare + nightly workflow to it; port goldens selectively. Smaller, conflict-free, no functionality removed; loses DB-as-Oracle and the portable package unless re-ported later.
  - C) **Hybrid** — close the branch but cherry-pick `eval.yml` and the Report/baseline compare (`evalkit/report.py`-style) onto the existing harness; leave the evalkit package as a future spec.
- default_if_no_response: BLOCK
- decision: KEEP the branch (variant of A). Merge `main` INTO `feat/agent-eval-pipeline` first and resolve the conflicts there; then, on top of the branch's existing plan + code, plan the refactor/update/improve work sized by how complex/correct the current codebase is against the requirements. Verbatim: "giữ nhánh này, merge code từ main vào trước (resolve merge conflict nếu có). sau đó dựa trên plan + code hiện tại để lên kế hoạch refactor/update/improve/etc tuỳ vào mức độ phức tạp/đúng đắn của codebase hiện tại và reqs"
- decided_by: Minh Tran (user, AskUserQuestion at intake)
- decided_at: 2026-09-07

## E002

- raised_by: orchestrator (feature-intake)
- date: 2026-09-07
- trigger: hard-gate (external-provider: paid LLM judge in GitHub Actions on a repo secret)
- question: Authorize a real judge key in CI and pick the cadence — nightly cron, manual `workflow_dispatch` only, or defer the judged run entirely?
- context: A FakeLLM cannot measure routing/quality (the routing decision *is* the LLM); the existing keyless smoke already runs in CI and only proves the pipeline. Any gate that can catch a prompt regression needs a keyed model: judge = `gpt-4o-mini` (G-Eval ×4 rubrics + tool correctness) plus the agent's own model per case. Requires an `OPENAI_API_KEY` GitHub secret and a spend ceiling the operator accepts.
- options:
  - A) **Nightly cron + `workflow_dispatch`**, judged matrix on the full golden set, spend bounded by case count (39 today / 84 with evalkit). Matches the review's "chạy judged eval nightly".
  - B) **`workflow_dispatch` only** — no automatic spend; a human triggers before/after prompt changes. Weaker regression net.
  - C) **Defer judged CI** — ship baseline + local `make eval-compare` only; revisit when Langfuse/LangSmith online eval (review §5) is chosen.
- default_if_no_response: BLOCK
- decision: C — do NOT put the judged eval on CI yet. No `OPENAI_API_KEY` secret, no nightly cron; ship the committed baseline + `make eval-compare` for local/keyed runs and revisit when Langfuse/LangSmith online eval is chosen.
- decided_by: Minh Tran (user, AskUserQuestion at intake)
- decided_at: 2026-09-07

## E003

- raised_by: orchestrator (feature-intake)
- date: 2026-09-07
- trigger: ambiguous-direction
- question: What is "the baseline" that gets committed, and what does a regression against it do?
- context: Judged G-Eval scores are non-deterministic run-to-run; a committed `latest.json` snapshot with a hard equality gate would flap. The evalkit branch's design uses a committed baseline + tolerance compare; the MIN-58 harness has no compare at all.
- options:
  - A) **Committed baseline JSON + tolerance regression gate** (per-metric / per-capability pass-rate floors, k-repeat averaged), refreshed by an explicit `make eval-baseline` commit. Nightly fails on drop beyond tolerance.
  - B) **Report-only** — nightly uploads the report as a workflow artifact and comments the delta; no failing gate; trend watched by a human.
  - C) **Baseline for deterministic metrics only** (routing/plan/tool-correctness with a real model) gated hard; judged rubrics report-only.
- default_if_no_response: BLOCK
- decision: A — committed baseline JSON + tolerance regression gate (per-metric / per-capability floors, k-repeat averaged), refreshed only by an explicit `make eval-baseline` commit.
- decided_by: Minh Tran (user, AskUserQuestion at intake)
- decided_at: 2026-09-07

## E004

- raised_by: intent-review (final review chain)
- date: 2026-09-07
- trigger: ambiguous-direction
- question: The review's "Sửa:" line asks to "chạy FakeLLM routing smoke trong CI với threshold"; intake recorded it as a false premise (a scripted FakeLLM proves plumbing, not routing) and the plan omitted it, and the legacy `tests/eval/test_eval_smoke.py` that asserted `ROUTING_THRESHOLD` was retired by the evalkit merge. Accept the omission, restore a plumbing smoke, or run a keyed smoke on CI?
- context: intent-review gap #1; E002 covers only the judged eval, not this clause.
- options:
  - A) accept the omission — keyless PR job stays `pytest tests/eval` + `--dry-run`; routing quality is measured only by the keyed `make eval-check`
  - B) restore a scripted FakeLLM smoke over routing.json with a threshold (plumbing proof only)
  - C) keyed smoke suite on PRs (contradicts E002)
- default_if_no_response: BLOCK
- decision: A — accept the omission (premise correction ratified by the user).
- decided_by: Minh Tran (user, AskUserQuestion)
- decided_at: 2026-09-07

