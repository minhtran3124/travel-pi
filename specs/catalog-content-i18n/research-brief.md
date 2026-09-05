# catalog-content-i18n — Research brief

Depth: **Deep** (intake lane high-risk: additive schema via Alembic). No upgrade during research.

## Source Pack

- none (local-only; no external surface) — no new dependency; the LLM translator already exists
  (`graph.translate_llm = pick("extract_memory")`), SQLAlchemy/Alembic/LangGraph versions unchanged.

## What exists (local map)

| Concern | Where | Finding |
|---|---|---|
| Language detection | `app/agents/supervisor.py` (`SupervisorIntent.language`, sticky `state["language"]`) | one detection per turn; literals `"en"` at 3 sites |
| Reply language | `app/agents/state.py::with_reply_language` | every sub-agent already replies in `state["language"]` — the agent's prose needs nothing |
| Panel localization | `app/streaming/panel_localizer.py` → `panels/<kind>.py::_localize_vi` | `places` translates `description` via LLM per place per emission; `hotels` only swaps bounded fields; `if language != "vi"` literal |
| Translator handle | `app/agents/graph.py:203` `compiled.translate_llm = pick("extract_memory")`; consumed in `mapper.py` | the only LLM dependency on the SSE path |
| Tool-side injected state | `app/tools/place_tools.py::resolve_place(user_id: Annotated[str, InjectedState("user_id")])`, `hotel_tools.py` (`preferences`) | pattern to copy for `language`; args-schema must declare the injected field (`docs/solutions/agent/explicit-args-schema-breaks-tool-injection.md`) |
| Tool-side LLM call | `app/tools/date_tools.py::_parse_via_llm` → `get_agent_llm("date_resolution")` | precedent for an LLM call inside a tool; **a NEW agent-config name must be seeded with a model or it 403s in Docker** (`docs/solutions/agent/new-agent-config-node-seeds-null-model.md`) → reuse `extract_memory` |
| Sessions in tools | `app/tools/_base.py::session_scope` | tool owns a short-lived session; write-back of translations fits here |
| Repo conventions | `app/repositories/base.py::Repo` (Session or sessionmaker) | new repo follows it |
| Migrations | `alembic/versions/` head `f3b7c9d1e5a2`; additive template `e3b7c5d9a1f4_add_agent_runs.py` | new revision `down_revision="f3b7c9d1e5a2"`, String ids/timestamps like siblings |
| Seed | `app/db/seed.py::seed_all` (idempotent `merge`) | add an optional translations pass reading a checked-in JSON |
| FE locales | `apps/web/src/i18n/config.ts` `locales = ["en","vi"]` | BE constant must parity-test against this file |
| Panel parity tests | `tests/streaming/test_places_panel.py` (CATEGORY_VI ↔ CATEGORY_META) | pattern for the languages parity test |
| Test env | `.env` keys leak into tests; use `OPENAI_API_KEY=` (empty), not `env -u` (memory: env-u-does-not-neutralize-dotenv-secrets) | all Verify rows use that guard |

## Risks found

- Double translation: if the tool localizes `description` and `panels/places.py::_localize_vi`
  still calls the translator, text is translated twice → the panel-side translation must be
  removed in the same change.
- `graph.translate_llm` removal touches `tests/agents/test_graph_translate_handle.py`,
  `tests/streaming/test_mapper_language.py`, `test_panel_language_e2e.py` — update, do not delete
  coverage of bounded swaps.
- MCP exposes the same tools; `language` arrives absent there → default must normalize to `en`
  and skip the DB lookup.
- FakeLLM offline: `with_structured_output` cycles `structured_responses`; batch translation
  must use a Pydantic list model so tests can script it.

## Lightest credible path

Additive table + repo + one service with `localize(entity_type, items, fields, language)`;
two tools gain an injected `language`; panel-side free-text translation and the SSE translator
plumbing are removed; a constants module replaces literals; seed gains an optional JSON pass.
