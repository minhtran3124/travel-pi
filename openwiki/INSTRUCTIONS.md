# OpenWiki brief — travel-pi

Control metadata for OpenWiki runs, not a wiki page. Read it for scope and
priorities; do not rewrite it during init, update or chat runs.

## What this wiki is for

A reader who knows the domain but not this codebase should be able to answer
"how does this part work today, and what proves it" without reading source
first. Pages orient, source and tests stay authoritative.

## Scope

Document:

- `apps/api/` — the HTTP surface, domain services, repositories, and the
  LangGraph agent with its tools, prompts, memory, streaming, RAG, MCP server
  and eval harness.
- `apps/web/` — App Router pages, the typed API client, the chat and SSE
  client, i18n and theming.
- Cross-cutting concerns: configuration, migrations and seeding, auth and
  tiers, rate limiting, CI workflows, the operator dashboard.

Do not document:

- `specs/` — per-feature planning history. Cite a spec only as the reason a
  rule exists, never as a description of current behaviour.
- `.claude/` — the engineering harness. It is excluded from git and is not
  part of the runtime.
- Generated or vendored artifacts: `apps/web/src/lib/api/schema.d.ts`,
  `openwiki/` itself, `node_modules/`, `__pycache__/`, build output.
- Individual Alembic revisions. Describe the migration policy on the data-layer
  page instead, and name a single revision only when its behaviour is
  surprising.

## Structure to keep

Eight groups plus a routing page. Do not re-group or rename them without
stating the reason in the update:

| Directory | Holds |
|---|---|
| `agent/` | graph and supervisor, specialists and tools, state and reply language, prompt registry, memory, guardrails, streaming and side panels, observability, RAG, LLM providers and per-agent config |
| `architecture/` | monorepo overview, request lifecycle, data layer and migrations, configuration |
| `concepts/` | auth and tiers, rate limiting and quotas |
| `domain/` | trips and budget, bookings/flights/hotels, destinations and travel information |
| `frontend/` | app shell and routing, chat client, i18n and theming, feature pages |
| `integrations/` | MCP server |
| `operations/` | local dev, Docker and CI; admin and dashboard |
| `testing/` | backend strategy, agent eval harness, frontend and e2e |

`quickstart.md` is the entry page and routes a task to the page that explains
that part of the system. Keep its routing table in sync whenever pages move.

## Priorities for an update

1. Prefer revising an existing page over adding one. Page count should stay
   stable unless a genuinely new subsystem lands.
2. Check the agent subsystem first. It changes fastest and carries the most
   non-obvious rules: `apps/api/app/agents/`, `app/tools/`,
   `app/prompts/active.yaml`.
3. Re-verify Claims whose evidence moved before rewriting the prose around
   them. A moved line range is not by itself a behaviour change.
4. Prefer deleting a stale paragraph over keeping it hedged.

## What counts as true here

- Every substantive statement needs repository evidence, preferably a bounded
  line range. Where a document under `techstacks/` or `docs/` disagrees with
  the implementation, follow the implementation and say so on the page.
- Do not describe planned work as shipped. A spec with no corresponding code is
  not behaviour: the trip-research deep agent is designed, but `deepagents` is
  not a dependency.
- Synthetic and deterministic behaviour is deliberate here. Flights, hotel
  availability and FX are generated from seed data on purpose; explain the
  mechanism rather than flagging it as a gap.
- When the code states an invariant and the reason for it, carry both. The
  comments in this repository hold most of the "why", and those are the highest
  value lines to preserve.

## Refresh

This repository runs no scheduled OpenWiki workflow. The wiki is refreshed
manually with `openwiki code --update` from a local checkout, so read the
generated pointer block in `AGENTS.md` with that in mind: its mention of a
scheduled workflow is boilerplate this repository does not use. Expect the wiki
to lag `main`, and re-read source whenever a page looks older than the code it
describes.

## Language

English, matching the run language `en`, even though the team also works in
Vietnamese. Keep identifiers, paths and command names verbatim.
