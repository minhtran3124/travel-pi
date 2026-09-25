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

- none

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
