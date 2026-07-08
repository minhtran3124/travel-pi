---
problem_type: failure
module: agent/prompts
tags: langgraph, prompts, supervisor, prompt-registry, active-yaml, versioned-prompts, silent-no-op
severity: critical
applicable_when: About to change the wording of any agent/supervisor system prompt loaded through the prompt registry (files under apps/api/app/prompts/<agent>/).
affects:
  - apps/api/app/prompts/supervisor/v5.md
supersedes: null
confidence: high
confirmed_at: 2026-07-08
---

## Applicable When

Changing the PROSE of an agent or supervisor system prompt that is loaded via
`registry.get("<agent>")` — i.e. anything under `apps/api/app/prompts/<agent>/` where an
`active.yaml` sits next to versioned `vN.md` files.

## Symptom

You edit `apps/api/app/prompts/<agent>/active.yaml` to change the prompt wording, rebuild
the graph, and the model's behavior is unchanged — the new prose never reaches the LLM. In
the worse case the name→version map is now malformed.

## Wrong Approach

Treating `active.yaml` as the prompt body and editing prose there. This is an easy trap:
in MIN-57 the PLAN's `<files>` manifest itself named `active.yaml` for a prompt-wording
change (a plan gap), which pointed the implementer at the wrong file.

## Why It Failed

`active.yaml` is only a **name→version pointer map**. `registry.get("supervisor")` resolves
that pointer to a versioned Markdown file and returns *its* text — for MIN-57 the active
prose lived in `apps/api/app/prompts/supervisor/v5.md`. Editing the YAML changes the pointer
table, not the prose the agent sees, and can break the map.

This is **distinct** from the already-documented "prompt `.md` edits need a graph rebuild"
([[langgraph-thread-reset-and-prompt-reload]]): there the fix reaches the right file but is
stale until rebuild; here the problem is editing the *wrong file entirely*.

## Correct Approach

Edit the versioned prose file the registry actually returns — the active `vN.md` (here
`v5.md`). Leave `active.yaml` untouched unless you are deliberately switching which version
is active. Before editing, confirm which file is live: check what version `active.yaml`
names / what `registry.get(<name>)` resolves to, then edit that `vN.md`. When a PLAN task's
`<files>` names `active.yaml` for a prose change, treat it as a manifest gap and redirect to
the active `vN.md`.

## Guardrail

`proposed:` Before editing any agent prompt for wording, resolve the registry pointer first
and edit the `vN.md` the active version names — never edit `active.yaml` for prose. A lint/
hook could warn when a diff modifies `app/prompts/*/active.yaml` beyond its version-pointer
keys.

## Related

- docs/solutions/agent/langgraph-thread-reset-and-prompt-reload.md
