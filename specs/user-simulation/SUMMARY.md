# user-simulation — Summary

Lane: high-risk
Confidence: high
Reason: hard gates auth (HTTP path to /agent/* needs a JWT per test persona via CurrentUserDep) and external-provider (Claude Code CLI as a runtime driver; a 2D rendering library would enter a dependency manifest); also multi-domain BE harness + FE UI.
Flags: auth, external systems, multi-domain, data model, weak proof
Affects: apps/api/app/routers/agent.py (/agent/chat, /agent/stream consumer), apps/api/eval + evalkit (possible new dataset source), apps/web or a new standalone UI, dev/test database isolation
Input-type: new initiative
Route: brainstorming → xia2 (Deep) → writing-plans → using-git-worktrees → subagent-driven-development
Escalate: no (E001–E004 decided 2026-09-25: HTTP+JWT now, standalone UI, live, claude -p script + skill)

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> tôi đnag có ý tưởng build giả lập môi trường cho chatbot travel.
> tức là sẽ tạo ra 1 môi trường có ng dùng ảo từ nhiều nơi, có kế hoạch du lịch, hỏi chatbot, ...
> nhưng có 1 vấn đề là tôi muốn tận dụng claude code quota thay cho việc chatbot dùng openai model
> hãy phân tích và tìm hiểu vấn đề này

(analysis turn concluded: the Claude Code quota drives the virtual users + grading; the chatbot stays on OpenAI as the system under test)

> ok, chạy feature-intake cho user-simulation đi
> notes: 1 cai toi muon nữa là sinh ra 1 simluate UI, kiểu làm ảnh 2D người di chuyển đến bàn chatbot rồi nói chuyện các kiểu bla bla ...

## What changed

Intake only — no code yet. Classified the initiative and opened ESCALATIONS.md for the direction choices that brainstorming needs before design.

### Rationale

Splitting the two LLM roles keeps the chatbot's real model (gpt-5.4-mini, which prompts and eval baselines are tuned on) as the system under test, while the token-heavy persona role-play and grading run on the user's Claude Code quota, a legitimate personal use of Claude Code.

### Alternatives considered

- Swap the chatbot's LLM to Claude via the subscription — rejected: `claude -p` is not a tool-calling chat API (would need a subscription-backed proxy, a ToS grey zone), and it changes the system under test.
- Chatbot on Claude via `LLM_PROVIDER=anthropic` + API key — legitimate, but paid per token, not quota; kept as a model-comparison option only.

### Deviations

- Rule 3 — `api-sim` uses `env_file: [{path: .env, required: false}]` so `docker compose config -q` validates in a worktree without `apps/api/.env` (Task 1.7, 91fa966d). The missing-key case is caught by the sim preflight (Task 3.1).
- Rule 1 — The sim-UI chip correlates tool results by `id`, which led to a contract amendment: design §5.7 `bot_tool` now carries `id`, and the driver fills in `name` on results and `reply` on `bot_done` (Tasks 1.3 and 1.6, e163934a, 12f16b84).
- Rule 1 — Only a `rejected` rate-limit status counts as quota exhaustion; `allowed_warning` just updates the gauge. Design §5.1 was aligned to match (Task 1.1, 2fe04570, 3cb33dcf).
- Controller correction — The Task 1.6 dispatch note allowed Google Fonts, which contradicted the plan's "no CDN" rule. The links were removed and the plan won (3d5e4b0f).

- Plan gap — Wave 2 tasks depend on each other (2.2 imports `Persona` from 2.1; 2.3 imports `SessionResult` from 2.2), so they ran in order 2.1 → 2.2 → 2.3 instead of in parallel.
- Contract amendments during review:
  - design §5.7 `persona_leave` gains the `aborted` reason (401, 429, or tier-setup failure);
  - §5.9 says aborted travellers walk out at once with no badge;
  - `set_tier` is called per traveller as `set_tier(persona_id)`;
  - any `book_*` tool maps the session to the `booking` capability (a plan-owner decision recorded in PLAN Task 2.3).
- Recorded decision — One traveller's `set_tier` failure aborts the whole batch as `tier_misconfigured`. This is conservative: it prevents a storm of free-tier 429s. Sessions that already finished are kept.
- Task 3.3 — `.claude/` is excluded from git (`.git/info/exclude`), so the launcher skill lives in the main checkout's `.claude/skills/user-sim/` alongside every other repo skill and is not part of the PR diff.

Open Minor findings (forwarded to the final review):
- 1.5: two test helpers keep multi-parameter signatures on one line; `make_url` is parsed twice in `sim_session_factory`.
- 1.7: the `required: false` long syntax needs Docker Compose 2.24 or later (local 5.4.0).
- 1.2: the wrong-signature test reads the private `KeyServer._kid`.

### Verify

| Check | Command | Exit | Notes | Criterion |
| --- | --- | --- | --- | --- |
| summary shape | `python .claude/scripts/verify_summary.py --lane user-simulation` | 0 | intake-time check | |

### Not auto-verified

- Claude subscription / Agent SDK usage terms (help-center monthly-credit article) — reached traceability only (cited by a research subagent); not re-read first-hand. xia2 must re-check them.

### Rollback

- `rm -rf specs/user-simulation` (intake artifacts only, nothing committed)

### Harness-Delta

- none
