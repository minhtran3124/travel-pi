---
slug: min-50-agent-stale-tool-results
status: shipped
owner: Minh Tran
created: 2026-07-03
---

# MIN-50 — Concierge exclude_names Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** When the traveller asks a dining/places follow-up like "any other places?", the concierge subagent gets genuinely different results instead of the identical list from the previous turn.

**Architecture:** Direction 1 (chosen over prompt-only Direction 2 and pagination Direction 3, see `specs/min-50-agent-stale-tool-results/SUMMARY.md` → Alternatives). Add an explicit `exclude_names: list[str] | None` argument to the `search_places` tool, threaded through `PlaceService.search_places`, filtering the already-sorted result set by name before returning. The concierge prompt is updated (new `v4.md`, active-version bump) to instruct the LLM to pass previously-suggested names as `exclude_names` on a follow-up, instead of repeating the identical call. `search_places` has no `InjectedState`/`InjectedStore` args today (confirmed — MIN-46's injection caveat doesn't apply), so `exclude_names` is added as a normal explicit LLM-supplied field, matching `city`/`category`/etc.

**Tech Stack:** FastAPI + LangGraph ReAct subagents, Pydantic v2 tool args (`langchain_core.tools.tool`), pytest with `FakeLLM` (scripted, no network) and a seeded SQLite temp DB (`seeded_session` / `agent_db` fixtures).

**Correction vs. intake:** `search_places` results are a plain DB query + Python sort over seeded `places` rows — **not** the MD5-hash-seeded generation CLAUDE.md forbids re-seeding (that constraint is about `flight`/`hotel` services). No conflict with that rule; noted for the record since `SUMMARY.md`'s Alternatives section framed it as a seed concern.

---

## 1. Motivation

MIN-50: the concierge subagent returns identical dining/place results on a "any other places?" follow-up because `search_places` has no way to exclude already-suggested items and nothing tells the agent to ask for different ones. See `specs/min-50-agent-stale-tool-results/SUMMARY.md` for full intake (Lane: normal, Confidence: medium, no hard gate).

## 2. Non-goals

- Direction 2 (prompt-only, no tool change) and Direction 3 (pagination/offset semantics) — evaluated and not chosen; see SUMMARY.md Alternatives.
- Guaranteeing the *real* LLM always complies with the new prompt instruction — that's a model-behavior question outside deterministic unit-test scope. This plan proves the **capability** works end-to-end when `exclude_names` is supplied (scripted `FakeLLM`), not live-LLM prompt adherence.
- Any change to the flight/hotel deterministic seed algorithm (untouched, out of scope).
- `nearby_places`, `resolve_place`, `parse_nl_query`, `list_place_categories` — unaffected, no `exclude_names` needed there per the Linear issue's scope (dining/places search only).

## 3. Success Criteria

- `search_places.invoke({"city": "Tokyo", "exclude_names": [...]})` omits the named places from its result.
- The concierge's active prompt instructs the model to pass already-suggested names as `exclude_names` on a follow-up "other places" style question.
- An end-to-end subagent-level test (scripted `FakeLLM` tool call carrying `exclude_names`) shows the excluded names do not reappear in the tool result flowing back into agent state.
- All new and existing tests pass: `cd apps/api && ../../.venv/bin/python -m pytest tests/services/test_place_service.py tests/prompts/test_concierge_prompt.py tests/tools/test_place_tools.py tests/agents/test_concierge_dedup.py -v`.

## 4. Tasks

### Task 1.1 — PlaceService.search_places exclude_names filter

```xml
<task id="1.1" wave="1">
  <files>apps/api/app/services/place_service.py, apps/api/tests/services/test_place_service.py</files>
  <action>
Add `exclude_names: list[str] | None = None` as a keyword-only param to `PlaceService.search_places`
(apps/api/app/services/place_service.py:95-105), documented in the docstring. After the repository
fetch (line 130-137) and before the sort dispatch (line 139), filter out any place whose `name` is
in `exclude_names` when it's truthy:

```python
results = self._place.search(
    city=resolved,
    category=category,
    min_rating=min_rating,
    price_level=price_level,
    price_level_max=price_level_max,
    recommended=recommended_only or None,
)

if exclude_names:
    excluded = set(exclude_names)
    results = [p for p in results if p.name not in excluded]

if sort == "rating_asc":
    ...
```

Add `:param exclude_names: Optional place names to omit from the results (e.g. items already
suggested this conversation).` to the docstring, next to the other `:param:` lines.

Step 1: Write the failing test in `apps/api/tests/services/test_place_service.py` (new file):

```python
"""PlaceService.search_places exclude_names filter (MIN-50)."""


def test_search_places_exclude_names_omits_matches(seeded_session):
    from app.services.place_service import PlaceService

    svc = PlaceService(seeded_session)
    baseline = svc.search_places(city="Tokyo")
    assert len(baseline) == 4

    excluded = [baseline[0].name, baseline[1].name]
    filtered = svc.search_places(city="Tokyo", exclude_names=excluded)

    assert len(filtered) == len(baseline) - 2
    assert not set(excluded) & {p.name for p in filtered}


def test_search_places_exclude_names_none_is_no_op(seeded_session):
    from app.services.place_service import PlaceService

    svc = PlaceService(seeded_session)
    with_none = svc.search_places(city="Tokyo", exclude_names=None)
    without_arg = svc.search_places(city="Tokyo")
    assert [p.name for p in with_none] == [p.name for p in without_arg]
```

Step 2: Run `cd apps/api && ../../.venv/bin/python -m pytest tests/services/test_place_service.py -v` —
expect FAIL (`TypeError: search_places() got an unexpected keyword argument 'exclude_names'`).

Step 3: Implement the filter as shown above.

Step 4: Re-run the same command — expect PASS.
  </action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/services/test_place_service.py -v</verify>
  <done>Both new tests pass; existing PlaceService tests (if any) still pass; exclude_names is a no-op when omitted or empty.</done>
</task>
```

### Task 1.2 — Concierge prompt: instruct exclude_names on follow-up

```xml
<task id="1.2" wave="1">
  <files>apps/api/app/prompts/concierge/v4.md, apps/api/app/prompts/active.yaml, apps/api/tests/prompts/test_concierge_prompt.py</files>
  <action>
This repo bumps prompt versions rather than editing active files in place (see git history:
"feat(supervisor): update routing logic and add v4 prompt"). Create
`apps/api/app/prompts/concierge/v4.md` as a copy of `v3.md` with one new paragraph inserted
directly after the existing "When a tool returns a list of options..." paragraph (currently
v3.md:30-31), before the "## Example — weather" section:

```markdown
When the traveller asks a follow-up like "any other places?", "what else?", or "something
different", don't repeat the same tool call with identical arguments. Pass the names you already
suggested into `exclude_names` on `search_places` so the tool returns fresh options instead of
the same list.
```

Bump `apps/api/app/prompts/active.yaml`: change `concierge: 3` to `concierge: 4`.

Step 1: Write the failing test in `apps/api/tests/prompts/test_concierge_prompt.py` (new file):

```python
"""Concierge follow-up dedup instruction (MIN-50)."""


def test_concierge_prompt_mentions_exclude_names_on_followup():
    from app.prompts.registry import registry

    text = registry.get("concierge")
    assert "exclude_names" in text
```

Step 2: Run `cd apps/api && ../../.venv/bin/python -m pytest tests/prompts/test_concierge_prompt.py -v` —
expect FAIL (v3.md doesn't mention `exclude_names`, so `registry.get("concierge")` still returns v3 text).

Step 3: Create `v4.md` and bump `active.yaml` as described above.

Step 4: Re-run — expect PASS. Also run `tests/prompts/test_registry.py -v` to confirm the version
bump didn't break `registry.get`/`names()` assumptions (concierge must still be in `registry.names()`).
  </action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/prompts/test_concierge_prompt.py tests/prompts/test_registry.py -v</verify>
  <done>Active concierge prompt (v4) instructs exclude_names on follow-up; v1-v3 remain retrievable via explicit version=.</done>
</task>
```

### Task 2.1 — search_places tool: exclude_names arg (depends on 1.1)

```xml
<task id="2.1" wave="2">
  <files>apps/api/app/tools/place_tools.py, apps/api/tests/tools/test_place_tools.py</files>
  <action>
Requires Task 1.1 done first (PlaceService must accept `exclude_names` before the tool can pass it
through). In `apps/api/app/tools/place_tools.py`:

1. Add a field to `SearchPlacesArgs` (after `price_level`, line ~33):

```python
    exclude_names: list[str] | None = Field(
        None,
        description=(
            "Place names to omit from the results — pass the names already suggested "
            "this conversation when the traveller asks for other/different options, "
            "instead of repeating the same search."
        ),
    )
```

2. Add the param to the `search_places` function signature (line 64-69) and thread it through to
`PlaceService(s).search_places(...)` (line 85-90), and add a matching `:param exclude_names:` line
to the docstring:

```python
@tool(args_schema=SearchPlacesArgs)
def search_places(
    city: str | None = None,
    category: str | None = None,
    min_rating: float | None = None,
    price_level: int | None = None,
    exclude_names: list[str] | None = None,
) -> list:
    """... (existing docstring lines unchanged) ...

    :param exclude_names: Place names to omit — pass prior suggestions on a follow-up.
    :return: Matching places.
    """
    log_tool_call("search_places", locals())
    with session_scope() as s:
        try:
            return dump(
                PlaceService(s).search_places(
                    city=city,
                    category=category,
                    min_rating=min_rating,
                    price_level=price_level,
                    exclude_names=exclude_names,
                )
            )
        except AppError as e:
            raise ToolException(str(e)) from e
```

Step 1: Append the failing test to `apps/api/tests/tools/test_place_tools.py`:

```python
def test_search_places_exclude_names_omits_matches(agent_db):
    from app.tools.place_tools import search_places

    baseline = search_places.invoke({"city": "Tokyo"})
    assert len(baseline) == 4

    excluded = [baseline[0]["name"], baseline[1]["name"]]
    filtered = search_places.invoke({"city": "Tokyo", "exclude_names": excluded})

    assert len(filtered) == len(baseline) - 2
    assert not set(excluded) & {p["name"] for p in filtered}
```

Step 2: Run `cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_place_tools.py -v` —
expect FAIL (unexpected keyword arg on schema/call, or `ValidationError`).

Step 3: Implement the changes above.

Step 4: Re-run — expect PASS, including all pre-existing tests in that file (schema-shape
assertions like `test_search_places_min_rating_bounds_in_schema` must still pass unchanged).
  </action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/tools/test_place_tools.py -v</verify>
  <done>search_places accepts exclude_names end-to-end (schema → tool → service); all pre-existing tool tests still green.</done>
</task>
```

### Task 3.1 — Reproduction test: concierge honors exclude_names end-to-end (depends on 1.2, 2.1)

```xml
<task id="3.1" wave="3">
  <files>apps/api/tests/agents/test_concierge_dedup.py</files>
  <action>
This is the reproduction test called for in the Linear issue's Triage TODOs. It scripts a `FakeLLM`
tool call that already carries `exclude_names` (simulating an LLM that followed the new v4 prompt
instruction from Task 1.2) and proves the plumbing from Task 2.1 delivers a filtered result back
into the agent's message state — i.e., the *capability* the fix ships is provably wired end-to-end,
independent of whether a live LLM reliably chooses to use it (see Non-goals).

Create `apps/api/tests/agents/test_concierge_dedup.py`:

```python
"""Concierge exclude_names wiring end-to-end (MIN-50 reproduction test)."""

from langchain_core.messages import AIMessage, HumanMessage


def test_concierge_exclude_names_omits_prior_suggestions(agent_db):
    from app.agents.subagents._base import build_subagent
    from app.clients.llm import FakeLLM
    from app.prompts.registry import registry
    from app.tools.registry import get_tools_for

    fake = FakeLLM(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_places",
                        "args": {
                            "city": "Tokyo",
                            "exclude_names": ["Senso-ji Temple", "Shibuya Crossing"],
                        },
                        "id": "c1",
                    }
                ],
            ),
            "Here are a couple more spots in Tokyo.",
        ]
    )
    subgraph = build_subagent(
        "test_concierge_dedup",
        get_tools_for("concierge"),
        lambda _: fake,
        registry.get("concierge"),
    )

    result = subgraph.invoke(
        {"messages": [HumanMessage(content="any other places in Tokyo?")]}
    )

    tool_msgs = [m for m in result["messages"] if m.__class__.__name__ == "ToolMessage"]
    assert tool_msgs, "expected search_places to be called"
    content = str(tool_msgs[-1].content)
    assert "Senso-ji Temple" not in content
    assert "Shibuya Crossing" not in content
```

Step 1: Write the test above (it should already pass once Tasks 1.1/1.2/2.1 are done — this task
is verification-only, no production code change).

Step 2: Run `cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_concierge_dedup.py -v` —
expect PASS. If it fails, the failure points at whichever upstream task (1.1/2.1) is incomplete —
fix there, not in this test.
  </action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/agents/test_concierge_dedup.py -v</verify>
  <done>End-to-end test proves excluded names are absent from the ToolMessage the concierge graph produces.</done>
</task>
```

## 5. Wave Plan

| Wave | Tasks | Parallelism |
|------|-------|-------------|
| 1 | 1.1 (service filter), 1.2 (prompt v4) | 2 parallel — disjoint files |
| 2 | 2.1 (tool schema, depends on 1.1's new service param) | single |
| 3 | 3.1 (reproduction test, depends on 1.2 + 2.1) | single |

## 6. Risks

- **Prompt compliance is not guaranteed.** The v4 instruction is a nudge, not a hard constraint — a
  live LLM may still repeat an identical call occasionally. Mitigation: the capability is now real
  and testable regardless (Task 3.1); prompt wording can be iterated later without further tool
  changes if compliance proves weak in practice (would need live-eval observation, out of scope
  here).
- **Case/whitespace mismatches in `exclude_names`.** The filter does an exact `str` match on `name`.
  If the LLM paraphrases a name slightly, the exclude won't match. Acceptable for v1 — the prompt
  tells the model to reuse the exact names it was given, which appear verbatim in prior tool
  results.

## 7. Status Log

- 2026-07-03 — Plan drafted, Direction 1 confirmed by user. Not yet executed.
- 2026-07-03 — All 3 waves executed and verified (19/19 tests pass). Task 3.1 deviation:
  `agent_db` fixture imported explicitly from `tests.tools.conftest` (see SUMMARY.md
  Deviations). Plan complete.
