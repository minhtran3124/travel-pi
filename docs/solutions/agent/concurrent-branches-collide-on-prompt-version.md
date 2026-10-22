---
problem_type: failure
module: agent/prompts
tags: prompts, prompt-registry, active-yaml, versioned-prompts, merge-conflict, concurrent-branches, concierge
severity: critical
applicable_when: Adding a new versioned prompt file under apps/api/app/prompts/<agent>/ while another branch targeting the same base is open, or resolving a merge conflict in which both sides added the same vN.md.
affects:
  - apps/api/app/prompts/concierge/v13.md
  - apps/api/app/prompts/concierge/active.yaml
supersedes: null
confidence: high
confirmed_at: 2026-09-09
---
## Applicable When

Two branches cut from the same base each add a prompt version for the same agent. The
version number is chosen by reading the directory at branch time, so both sides
independently pick the next free number.

## Symptom

PR #172 conflicted with `main` after PR #171 merged. Both had added
`apps/api/app/prompts/concierge/v12.md` with entirely different prose, and both had
pointed `active.yaml` at `v12`. Git reported a plain add/add conflict on the file and a
one-line conflict in the YAML — which looks trivial and invites the wrong resolution.

## Wrong Approach

Resolving it as an ordinary text conflict: merging the two prompt bodies into a single
`v12.md`, or keeping "mine" because it is newer. Both destroy information. Merging the
bodies produces a prompt no one wrote and no eval covered. Keeping "mine" silently
reverts the routing rules the other branch shipped and already validated.

## Why It Failed

A versioned prompt file is an immutable artifact, not a mutable source file. `v12` is a
name that has already been published, referenced by the merged commit and by whatever
eval baseline ran against it. Overwriting it makes the repository's history claim a
version contains text it never contained. And because `active.yaml` is only a pointer,
the conflict resolution that *looks* smallest — take one side of a single YAML line — is
the one that quietly drops a whole prompt.

## Correct Approach

Treat the merged side as immutable and rebase your own work onto the next free number:

1. Keep `main`'s `v12.md` byte-for-byte. Do not touch it.
2. Re-apply your changes as a new `v13.md`, written **on top of** main's v12 rather than
   on top of your pre-conflict draft — otherwise you drop whatever main's version added.
   Here that meant carrying forward main's hotel-tool routing while adding the visa-tool
   rule this branch introduced.
3. Point `active.yaml` at `v13`.
4. Rebuild the graph before verifying: `docker exec api-api-1 touch app/main.py`. The
   registry is a singleton and the graph is baked at lifespan startup, so a prompt edit
   is invisible to the running agent until then.

## Guardrail

`proposed:` a pre-commit check that rejects a staged new `apps/api/app/prompts/<agent>/vN.md`
whose `N` already exists on the merge base's remote branch, and that rejects an `active.yaml`
pointer to a version not present in the working tree. Target path:
`.claude/hooks/prompt-version-collision.sh`.

## Related

- docs/solutions/agent/supervisor-active-yaml-is-a-pointer.md
- docs/solutions/agent/langgraph-thread-reset-and-prompt-reload.md
- docs/solutions/harness/negative-grep-is-not-absence.md
