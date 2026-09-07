# tool-error-hint-propagation — Summary

Lane: high-risk
Confidence: high
Reason: Re-classified from `normal` after `hooks/risk-corroboration.sh` blocked the commit — the diff removes 27 `raise` lines, which trips the weakening-validation hard gate. Semantically nothing is weakened (each removed `raise` is replaced by another raise carrying strictly more information), but a declared lane below high-risk cannot be self-downgraded past a fired gate, so the lane is raised rather than the gate routed around. `RISK_WARN_CATEGORIES` set inline on `git commit` does not reach the PreToolUse hook, so that escape hatch is unavailable here.
Flags: existing behavior, multi-domain, weakening-validation (mechanical detection; see Reason)
Affects: `app/tools/_base.py` (shared tool helper), all 10 `app/tools/*_tools.py` modules
Input-type: change request

> `Lane` drives **ceremony** (how much proof). `Confidence` drives **interruption**
> (whether a human is asked). A hard gate forces `high-risk`. Low confidence or an
> ambiguous direction escalates regardless of lane — see `rules/orchestration.md`.

### Intent

> - AppError.__str__ chỉ trả detail, nên mọi hint= viết cho model đều bị mất trên đường tool
> (ToolException(str(e)) — dùng ở mọi tool trong repo). Tôi phát hiện khi con trỏ get_climate
> của chính mình không tới được model, và đã né bằng cách đưa vào detail. Nhưng đây là vấn đề
> toàn repo, chưa sửa.
>
> ---> update cho toan repo

### What changed

New `tool_error(e: AppError) -> ToolException` in `app/tools/_base.py` folds `detail` and `hint`
into the single string the model reads, called as `raise tool_error(e) from e` so `__cause__` is
preserved. All 27 `except AppError` sites across the 10 tool modules now go through it. With no
hint the output is identical to `str(e)`, so hint-less errors are unaffected. The 9
`except ValueError` sites are untouched — plain `ValueError` has no hint. `app/exceptions.py` is
unchanged.

### Rationale

`AppError.__init__` calls `super().__init__(self.detail)`, so `str(e)` returns the detail alone
and drops `hint`. Every tool surfaces domain failures as `ToolException(str(e))`, so **29 hints
written specifically for the agent never reach it**. The class docstring even claims the hint "is
surfaced in the error envelope so the agent can act on it" — true for the HTTP envelope, false on
the tool path, which is the path the agent actually uses.

Fixing it in one shared helper in `app/tools/_base.py` rather than editing `AppError.__str__`:
changing `__str__` would alter every log line and HTTP message repo-wide for a problem that only
exists at the tool boundary. The helper keeps the blast radius where the defect is.

Found while fixing MIN-66, where the `get_climate` recovery pointer had to be smuggled into the
detail to reach the model. That workaround becomes unnecessary once this lands, but is left in
place — it reads fine either way.

### Alternatives considered

- Change `AppError.__str__` to append the hint — rejected: alters logs and HTTP messages repo-wide
  to fix a tool-boundary problem.
- Edit all 27 sites inline without a helper — rejected: duplicates the formatting decision 27
  times, which is how these things drift.
- Leave it and document — rejected; the user asked for the repo-wide fix.

### Deviations

- The implementing subagent returned without its required report, so every claim below was
  re-verified independently rather than taken on trust.
- No Rule 1–3 code auto-fixes were needed.

### Verify

| Check | Command | Exit | Notes |
| --- | --- | --- | --- |
| Full backend suite | `pytest -q` (with `.env` aside) | 0 | **1744 passed, 0 failed** |
| Lint | `ruff check app` | 0 | clean |
| Hint reaches the model end-to-end | `get_weather.ainvoke({'city':'Zzzznotacity'})` | 0 | `str(e)` → `"Could not find a location named 'Zzzznotacity' Hint: Check the spelling, or use GET /cities?q=…"` — previously the hint was dropped |
| Cause chain preserved | same invocation, `type(e.__cause__)` | 0 | `CityNotFoundError` |
| All `AppError` sites converted | `grep -B2 "ToolException(str(e))" app/tools/ \| grep -c "except AppError"` | 0 | 0 remaining (was 27) |
| `ValueError` sites untouched | same grep for `except ValueError` | 0 | 9, unchanged |
| `app/exceptions.py` unchanged | `git diff --stat app/exceptions.py` | 0 | empty |

### Rollback

- `git revert <sha>` — no schema or migration; error text only.

### Harness-Delta

- none
