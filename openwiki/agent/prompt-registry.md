---
type: concept
title: Prompt registry and versioning
description: How agent system prompts are stored as versioned Markdown files per name, selected by the active.yaml pointer through the in-memory PromptRegistry, composed with the shared communication_style guideline, snapshotted into the compiled graph for run attribution, browsed and diffed in the dashboard, and how to change a prompt safely.
tags: [prompts, versioning, active-yaml, registry, communication-style, attribution, dashboard]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-18T04:47:06.927Z
sources:
  - id: openwiki-source-a9279e30fdd03870c290e7ae
    resource: repo://apps/api/app/agents/graph.py
  - id: openwiki-source-601069c231d7cd08336d73cc
    resource: repo://apps/api/app/agents/prompt_map.py
  - id: openwiki-source-0e29236b52482e5a3cdf5f04
    resource: repo://apps/api/app/agents/subagents/_base.py
  - id: openwiki-source-bc57b896f707caa4b8b3d2de
    resource: repo://apps/api/app/core/prompt_diff.py
  - id: openwiki-source-e7317a4ccae3a82e1c04a093
    resource: repo://apps/api/app/prompts/active.yaml
  - id: openwiki-source-adc78fd83aa2c3e21852cbe6
    resource: repo://apps/api/app/prompts/CHANGELOG.md
  - id: openwiki-source-3dd15222b15a78ae0fd5afd5
    resource: repo://apps/api/app/prompts/registry.py
  - id: openwiki-source-2439a13a4b07570637979de8
    resource: repo://apps/api/app/routers/dashboard_prompts.py
  - id: openwiki-source-931f7405d7b20b3a9f34c28c
    resource: repo://apps/api/tests/agents/test_prompt_map.py
  - id: openwiki-source-97ce94567b00612e183ae31c
    resource: repo://apps/api/tests/agents/test_prompt_versions_snapshot.py
  - id: openwiki-source-464a81abaccb3ce587550280
    resource: repo://apps/api/tests/prompts/test_active_versions_load.py
  - id: openwiki-source-dccca3c54b21933c3cd93e67
    resource: repo://apps/api/tests/prompts/test_registry.py
  - id: openwiki-source-ce832f71ed7667f20d661308
    resource: repo://apps/api/tests/prompts/test_supervisor_prompt.py
generated: { by: "claude-code", at: "2026-09-18T04:47:06.927Z" }
---

# Prompt registry and versioning

All model-facing instructions live under `apps/api/app/prompts/` as **files, not database rows**: one directory per prompt name (`supervisor`, `planner`, `concierge`, `journal`, `booking`, `budget`, `reflection`, `memory_extraction`, `date_resolution`, `communication_style`) containing `v1.md`, `v2.md`, … , plus a single `active.yaml` that maps each name to the version that is live. Old versions are kept for rollback and A/B comparison; `CHANGELOG.md` in the same directory records why each version exists, newest first.

## The registry

`PromptRegistry` (`app/prompts/registry.py`) scans `*/v*.md` at import time into an in-memory `{name: {version: text}}` map and reads `active.yaml` into an active-version map; no runtime database is involved. A module-level singleton `registry` is what every caller imports.

- `get(name, version=None)` returns the active version's text, or the **newest** version when `active.yaml` has no entry for that name; an unknown name or version raises `KeyError`.
- `names()`, `versions(name)` and `active_version(name)` back the dashboard and the attribution snapshot.
- `reload()` re-scans the directory and re-reads `active.yaml`, but nothing in the app calls it at runtime; prompts are read once per process, so a prompt change needs a process restart (or a graph rebuild in Docker, where touching `app/main.py` triggers uvicorn's reload).

`tests/prompts/test_registry.py` pins active-version resolution, explicit versions, the two error cases and `reload`; `test_active_versions_load.py` asserts that **every entry in `active.yaml` resolves to non-empty text**, which is the guard against a pointer to a version file that was never committed.

## The pointer is the switch

Because `get()` resolves through `active.yaml`, **editing a `vN.md` in place that `active.yaml` does not point to is a silent no-op**, and adding `v14.md` without bumping the pointer changes nothing. The working convention is therefore: copy the current version to a new `vN+1.md`, edit it, bump `active.yaml`, add a `CHANGELOG.md` entry, and add or update a prompt test that asserts the new behaviour by content (see `tests/prompts/test_supervisor_prompt.py`, which is parametrized over versions and checks for specific rule text such as the concierge-only tool carve-out and the explicit language-switch rule). Two branches that both add the same `vN.md` collide on merge, so check the highest existing version before naming a file.

## Composition at build time

Prompts are read when the graph is compiled, not per turn:

- The **supervisor** node wraps `registry.get("supervisor")` in its `SystemMessage` and appends the established conversation language and the current-date grounding per turn (see [Agent graph and supervisor routing](graph-and-supervisor.md)).
- Every **specialist** is built with `f"{communication_style}\n\n{domain prompt}"`: the shared `communication_style` guideline (assistant identity "Tin", language rules, reply shape) is prepended to each domain prompt in `_make_subagent`, so a style change applies to all five specialists at once. Per turn, `system_with_summary`, `with_reply_language`, date grounding and the supervisor's task note are layered on top, with the volatile parts placed last so the cacheable prefix stays stable (see [Agent state, runtime context and reply language](state-context-and-language.md)).
- **reflection** and **memory_extraction** read their prompts the same way; `date_resolution` is read by the date tool that makes its own LLM call.

The LLM behind each prompt is chosen separately, per node, from the DB-backed agent config (see [LLM providers and per-agent configuration](llm-providers-and-agent-config.md)).

## Attribution: the build-time snapshot

`prompt_versions_snapshot(registry)` (`app/agents/prompt_map.py`) records `{name: active_version}` for every registered name, and `build_graph` stores it on the compiled graph as `prompt_versions`. The agent router copies that snapshot onto each `agent_runs` row and `enrich_steps` attaches per-step `{name, version}` pointers using `PROMPTS_FOR_NODE`, a static map from node key to the prompts that node composes. The map keys use the `<ns_root>/<node>` form the metrics handler produces, because every specialist's inner node is called `assistant` and a bare name would collapse all five; specialist keys map to `[<specialist>, communication_style]`, root `supervisor`/`reflection` map to their own prompt, and promptless nodes (`pii_guardrail`, `load_context`, `plan`, `summarize`, `synthesize`, `tools`, `trip_guard`) map to `[]`. A `synthesis_worker` step carries its specialist in metadata and is re-keyed onto `<specialist>/assistant`.

`tests/agents/test_prompt_versions_snapshot.py` asserts the snapshot is taken at build, not read per turn, so a pointer bump after startup cannot misattribute in-flight runs; `test_prompt_map.py` asserts the map covers exactly the graph's node keys and that every mapped name is registered. See [Observability, turn metrics and cost](observability-and-metrics.md).

## Browsing and diffing in the dashboard

`app/routers/dashboard_prompts.py` serves three HTML routes, excluded from the OpenAPI schema and protected by the dashboard's basic auth: `/prompts` lists every name with its active version, `/prompts/{name}?version=vN` shows one version (defaulting to the latest, and pre-selecting the previous version as the comparison base), and `/prompts/{name}/diff?from=vA&to=vB` renders a unified and side-by-side line diff produced by `build_line_diff` in `app/core/prompt_diff.py` (stdlib `difflib`). Unknown names or versions become `NotFoundError`. The dashboard is read-only for prompts; there is no edit endpoint. See [Admin API and server-rendered dashboard](../operations/admin-and-dashboard.md).

## Verifying a prompt change

Prompt tests check content, not behaviour. Behavioural verification is the eval harness: run `make eval-smoke` for a keyless trajectory check and `make eval-check` (judged, paid) before merging a prompt change, and read which metrics a golden declares rather than trusting its name or notes (see [Agent evaluation harness](../testing/agent-eval-harness.md)). A prompt-driven behaviour that seems to persist across turns in a dev thread is often a poisoned checkpoint rather than the prompt; start a fresh conversation after a reload.
