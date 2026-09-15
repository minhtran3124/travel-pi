# state-md-auto-update-on-merge — Research brief

Depth: **Deep** (intake lane high-risk; high-blast hook + a CI job with `contents: write`).

## Local map

- `.claude/runtime/run_state.py` — engine. `FORWARD_TRANSITIONS["ready_to_merge"] = {"shipped"}` (l.271);
  `shipped` requires `sha` matching `^[0-9a-f]{7,40}$` (l.274, l.817); `validate_chain` 9 invariants
  (l.368–470: contiguous seq, from_state chains, constant slug/run_id, genesis `queued`, legal hop,
  unique event_id, string event, shipped sha, runtime-metadata pair); `project()` fields: slug, run_id,
  state, seq, waiting_on, resume_event, sha (last non-empty), created_at (first ts), updated_at (last
  ts), last_event_id, optional runtime pair. Event lines are `json.dumps(sort_keys=True)`; RUN.json is
  `indent=2, sort_keys=True` + newline.
- Harness is NOT in git: `git ls-files .claude` → only `settings.json`; `.git/info/exclude:27` has
  `.claude/`. So CI cannot import the engine → self-contained script (design decision).
- Hook source: `harness-skills/hooks/state-breadcrumb.sh` (identical to travel-pi's copy),
  deployed by `harness-skills/scripts/deploy-harness.sh`, whose conflict default is "keep mine".
- STATE.md readers: `resume_decision.py:858` reads only `## Active Spec`. No reader of
  "Session End Log" found (`grep -rn 'Session End Log' .claude` for *.md/*.sh/*.py → only the hook);
  `session-tracker` is listed in `.claude/skills/README.md:144` but no such skill dir exists in
  `.claude/skills/` or `~/.claude/skills/`.
- Slug resolution evidence: PR files API lists `specs/<slug>/RUN.json` for #206, #196; branch-prefix
  strip maps 11/15 recent merged PRs to an existing `specs/<slug>/` dir; the rest are chore/docs.
- Repo: private, free plan → branch-protection/rulesets API 403 (no protection on main);
  `default_workflow_permissions: read`; `ci.yml` is `on: pull_request` only.

## Source Pack

- GitHub Docs — Events that trigger workflows, `pull_request` (merge pattern: `types: [closed]` +
  `if: github.event.pull_request.merged == true`; for closed+merged, GITHUB_SHA = last merge commit,
  GITHUB_REF = base branch; fork PRs get a read-only GITHUB_TOKEN).
  https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows
- GitHub Docs — Triggering a workflow: "events triggered by the GITHUB_TOKEN will not create a new
  workflow run" (exceptions: workflow_dispatch, repository_dispatch) → the bot push cannot recurse.
  https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/triggering-a-workflow
- GitHub Docs — Security hardening: pass untrusted context (e.g. PR head ref/title) via `env:`, not
  inline `${{ }}` in `run:`; default token read-only, raise per job.
  https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions

## Risks

- Bot push races a human push to main → `pull --rebase` retry ×3, then fail loudly.
- Feature branches that also edit STATE.md can conflict with bot commits → bot edits only one table
  row and (when matching) three Active Spec bullets; B removes the main conflict source (the log).
- Engine drift: if run_state.py changes its projection, the script must follow → engine-backed test.
- The workflow only exists once it is on main; merges before that are not processed.
