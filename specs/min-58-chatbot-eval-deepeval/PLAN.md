---
slug: min-58-chatbot-eval-deepeval
status: shipped
owner: Minh Tran
created: 2026-07-06
---

# DeepEval + G-Eval Offline Eval Harness (MIN-58) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans / subagent-driven-development to implement this plan task-by-task.

**Goal:** Add a DeepEval + G-Eval offline evaluation layer under `apps/api/eval/` — natural-language G-Eval rubrics + `ToolCorrectnessMetric`, a graph→`LLMTestCase` harness, ~15-20 datasets, and a keyed runner — without changing production agent code and without breaking the no-network routing smoke.

**Architecture:** Layer DeepEval *alongside* the existing `eval/run_eval.py` (routing-accuracy, no-network FakeLLM smoke — left untouched). New modules follow `run_eval.py`'s dependency-injection split: pure/inject-deps functions are unit-tested with `FakeLLM` (no network); `main()` builds the real graph + real OpenAI judge and runs only when a real key is present. Judge = OpenAI `gpt-4o-mini` passed as a `model=` string (DeepEval-native, so **no** custom `DeepEvalBaseLLM` adapter now).

**Tech Stack:** DeepEval (`GEval`, `ToolCorrectnessMetric`, `LLMTestCase`, `ToolCall`, `evaluate`), LangGraph 1.x (`build_graph`, `MemorySaver`, `InMemoryStore`), LangChain 1.x messages, pytest 9.

---

## 1. Motivation

The Travel Assistant has no systematic output-quality gate — only ad-hoc manual case testing. Known failure modes (MIN-51 search-vs-booking intent, MIN-57 response language, MIN-46 tool args_schema, MIN-54 format) recur with no regression net. This builds the **offline foundation**: a runnable DeepEval harness + datasets + G-Eval rubrics. (See `research-brief.md` for the reuse analysis; `SUMMARY.md` for the five confirmed scoping decisions.)

## 2. Non-goals

- **No baseline run** against a real provider (deferred — avoids API spend now).
- **No CI wiring**, **no how-to doc** (follow-up after the harness is trusted).
- **No custom `DeepEvalBaseLLM` adapter** (judge is OpenAI-native; deferred until a non-OpenAI judge is needed).
- **No runtime self-evaluation / RubricMiddleware** — that is Phase 2, **MIN-59** (deepagents-specific, not portable to raw LangGraph).
- **No change to production agent code** or to `eval/run_eval.py` / `eval/metrics.py`.

## 3. Success Criteria

- `deepeval` pinned in `requirements-ai.txt` and installed **without** bumping fastapi/starlette/pydantic past their caps (`pip check` clean).
- `eval/metrics_geval.py`, `eval/harness.py`, `eval/run_deepeval.py`, `eval/datasets/*.json` exist with passing unit tests (all no-network).
- `python -m eval.run_deepeval` **skips gracefully** (exit 0, prints a skip notice) when no real OpenAI key is present; the existing routing smoke still passes.
- `../../.venv/bin/python -m pytest tests/eval -x` green.

## 4. Tasks

### Task 1.1 — Dependency spike: pin `deepeval` without breaking caps (Deep gate)

```xml
<task id="1.1" wave="1">
  <files>apps/api/requirements-ai.txt</files>
  <action>
DEEP GATE — run first; if caps break, STOP and escalate (do NOT nudge fastapi/starlette/pydantic caps; that rule is in requirements-ai.txt's header).

1. From repo root, install into the shared venv and probe resolution:
   `./.venv/bin/pip install "deepeval" 2>&1 | tail -20`
2. Verify the core caps still hold AND the dependency tree is consistent:
   `./.venv/bin/pip check`
   `./.venv/bin/python -c "import fastapi, starlette, pydantic; from packaging.version import Version as V; assert V(fastapi.__version__) < V('0.137'), fastapi.__version__; assert V(starlette.__version__) < V('1.3'), starlette.__version__; assert V(pydantic.VERSION).major == 2, pydantic.VERSION; print('caps-ok', fastapi.__version__, starlette.__version__, pydantic.VERSION)"`
3. If step 2 fails (a cap was exceeded or `pip check` reports a conflict): STOP. Write an ESCALATIONS.md block (option A: separate eval venv/extra; option B: pin an older deepeval) and do not proceed. Do NOT edit the caps.
4. If clean: read the installed version (`./.venv/bin/pip show deepeval | grep -i version`) and add a pin under a new "# Offline evaluation (MIN-58)." comment block in requirements-ai.txt, e.g. `deepeval>=X.Y,<X+1` using the installed major. Keep it grouped, with a one-line rationale comment noting it is eval-only tooling with an OpenAI-native judge.
  </action>
  <verify>cd apps/api && ../../.venv/bin/pip check && ../../.venv/bin/python -c "import deepeval, fastapi, starlette, pydantic; from packaging.version import Version as V; assert V(fastapi.__version__)<V('0.137') and V(starlette.__version__)<V('1.3') and V(pydantic.VERSION).major==2; print('ok', deepeval.__version__)"</verify>
  <done>deepeval imports; caps intact; pip check clean; version pinned in requirements-ai.txt.</done>
</task>
```

### Task 2.1 — G-Eval + ToolCorrectness metrics module

```xml
<task id="2.1" wave="2">
  <files>apps/api/eval/metrics_geval.py, apps/api/tests/eval/test_metrics_geval.py</files>
  <action>
Create `eval/metrics_geval.py` defining the offline judge config + metric factory. Judge model is the OpenAI-native string constant; no custom adapter. Thresholds are per-metric.

```python
"""G-Eval + tool-correctness metrics for the offline eval harness (MIN-58).

Judge = OpenAI `gpt-4o-mini` passed as a `model=` string (DeepEval-native, no
custom DeepEvalBaseLLM adapter). GEval derives evaluation steps from the
natural-language `criteria`. `ToolCorrectnessMetric` is deterministic (no judge).
Building these objects does no network I/O; only `.measure()` / `evaluate()` does.
"""

from __future__ import annotations

from deepeval.metrics import GEval, ToolCorrectnessMetric
from deepeval.test_case import LLMTestCaseParams

JUDGE_MODEL = "gpt-4o-mini"  # OpenAI-native judge; swap via a custom model later (MIN-58 follow-up)
DEFAULT_THRESHOLD = 0.7

_IO = [LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT]


def response_language_metric() -> GEval:
    """Answer must be in the same natural language as the user's input (MIN-57)."""
    return GEval(
        name="Response Language",
        criteria=(
            "Determine whether the actual output is written in the SAME natural "
            "language as the input. If the input is Vietnamese, the answer must be "
            "Vietnamese; if English, English. Penalize any answer that switches "
            "language or mixes languages against the user's language."
        ),
        evaluation_params=_IO,
        threshold=DEFAULT_THRESHOLD,
        model=JUDGE_MODEL,
    )


def search_vs_booking_metric() -> GEval:
    """Search intent must not be answered with booking/payment prompts (MIN-51)."""
    return GEval(
        name="Search vs Booking Intent",
        criteria=(
            "The input is a hotel/flight SEARCH or information request, not a "
            "confirmed booking. A good answer presents options/results. Penalize "
            "answers that push booking, ask for payment/passport/guest details, or "
            "assume the user already decided to book."
        ),
        evaluation_params=_IO,
        threshold=DEFAULT_THRESHOLD,
        model=JUDGE_MODEL,
    )


def no_hallucination_metric() -> GEval:
    """No invented hotel/flight facts not grounded in tool results."""
    return GEval(
        name="Fact Grounding",
        criteria=(
            "Penalize the actual output if it invents specific hotel or flight "
            "names, prices, times, or availability that a real tool call would "
            "supply. Generic guidance is fine; fabricated concrete facts are not."
        ),
        evaluation_params=_IO,
        threshold=DEFAULT_THRESHOLD,
        model=JUDGE_MODEL,
    )


def format_quality_metric() -> GEval:
    """Important info emphasized, tidy structure, tasteful emoji (MIN-54)."""
    return GEval(
        name="Format Quality",
        criteria=(
            "A good answer emphasizes important information (prices, dates, hotel/"
            "flight names) with bold, uses tidy structure (short paragraphs or "
            "lists) and tasteful emoji — not a dense wall of plain text."
        ),
        evaluation_params=_IO,
        threshold=DEFAULT_THRESHOLD,
        model=JUDGE_MODEL,
    )


def tool_correctness_metric() -> ToolCorrectnessMetric:
    """Deterministic: compares tools_called vs expected_tools (MIN-46). No judge."""
    return ToolCorrectnessMetric()


# Registry: metric-name -> factory. Runners select by dataset needs.
GEVAL_METRICS = {
    "response_language": response_language_metric,
    "search_vs_booking": search_vs_booking_metric,
    "no_hallucination": no_hallucination_metric,
    "format_quality": format_quality_metric,
}
```

TDD:
1. Write `tests/eval/test_metrics_geval.py` FIRST (network-free — only builds objects, never `.measure()`):

```python
from deepeval.test_case import LLMTestCaseParams

from eval.metrics_geval import (
    JUDGE_MODEL,
    GEVAL_METRICS,
    response_language_metric,
    tool_correctness_metric,
)


def test_judge_is_openai_native_string():
    assert JUDGE_MODEL == "gpt-4o-mini"


def test_geval_registry_has_four_dimensions():
    assert set(GEVAL_METRICS) == {
        "response_language",
        "search_vs_booking",
        "no_hallucination",
        "format_quality",
    }


def test_response_language_metric_shape():
    m = response_language_metric()
    assert m.name == "Response Language"
    assert LLMTestCaseParams.INPUT in m.evaluation_params
    assert LLMTestCaseParams.ACTUAL_OUTPUT in m.evaluation_params
    assert m.threshold == 0.7


def test_tool_correctness_is_deterministic_metric():
    # Constructs without a judge model (no OpenAI key needed).
    assert tool_correctness_metric() is not None
```

2. Run: `../../.venv/bin/python -m pytest tests/eval/test_metrics_geval.py -x` → expect FAIL (module missing), then PASS after creating the module. (No `tests/eval/__init__.py` needed — `tests/eval/` already exists and the repo collects test subdirs without per-dir `__init__.py`, e.g. `tests/agents/`.)
  </action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_metrics_geval.py -x</verify>
  <done>Four GEval factories + registry + ToolCorrectness build with no network; tests green.</done>
</task>
```

### Task 2.2 — Graph → LLMTestCase harness

```xml
<task id="2.2" wave="2">
  <files>apps/api/eval/harness.py, apps/api/tests/eval/test_harness.py</files>
  <action>
Create `eval/harness.py`: drive the compiled graph for one dataset case and build a DeepEval `LLMTestCase`. Follow `run_eval.py`'s inject-deps pattern so tests use a FakeLLM-backed graph (no network); `build_eval_graph()` builds the real one for `main()`.

Extraction rules (from app/routers/agent.py): reply = last `AIMessage.content`; `current_flow` = `out["current_flow"]`; tools = every `AIMessage.tool_calls[*]["name"]` across `out["messages"]`. Each case gets a UNIQUE thread_id (else checkpointer history bleeds across cases).

```python
"""Drive the travel graph and build DeepEval LLMTestCases (MIN-58).

`run_case(graph, case, index)` invokes the compiled graph for one dataset item
and returns an `LLMTestCase` (input, actual_output, tools_called, expected_tools,
context) plus the routed `current_flow`. Dependency-injected so tests drive a
FakeLLM-backed graph with zero network; `build_eval_graph()` builds the real one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from deepeval.test_case import LLMTestCase, ToolCall
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.context import AgentContext


@dataclass
class EvalResult:
    """One evaluated case: the DeepEval test case + the routed flow."""

    test_case: LLMTestCase
    current_flow: str | None


def _final_reply(messages: list[Any]) -> str:
    ai = [m for m in messages if isinstance(m, AIMessage)]
    return (ai[-1].content or "") if ai else ""


def _tools_called(messages: list[Any]) -> list[ToolCall]:
    names: list[str] = []
    for m in messages:
        for tc in getattr(m, "tool_calls", None) or []:
            name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
            if name:
                names.append(name)
    return [ToolCall(name=n) for n in names]


def run_case(graph: Any, case: dict, index: int) -> EvalResult:
    """Invoke *graph* for one dataset *case* and build its LLMTestCase.

    :param graph: A compiled travel graph (real or FakeLLM-backed).
    :param case: Dataset item; requires ``input``; optional ``expected_tools``,
        ``context``.
    :param index: Position in the dataset — used to mint a unique thread_id.
    :return: An :class:`EvalResult`.
    """
    cfg = {"configurable": {"thread_id": f"eval-{index}"}}
    out = graph.invoke(
        {"messages": [HumanMessage(content=case["input"])], "user_id": "eval", "trip_id": None},
        cfg,
        context=AgentContext(),
    )
    messages = out["messages"]
    expected = [ToolCall(name=n) for n in case.get("expected_tools", [])]
    test_case = LLMTestCase(
        input=case["input"],
        actual_output=_final_reply(messages),
        tools_called=_tools_called(messages),
        expected_tools=expected,
        context=case.get("context"),
    )
    return EvalResult(test_case=test_case, current_flow=out.get("current_flow"))


def build_eval_graph() -> Any:
    """Build the REAL travel graph for eval (nodes resolve real providers).

    Uses in-memory checkpointer/store — eval is single-shot per case, no
    persistence needed. Requires a configured provider key at call time.
    """
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.store.memory import InMemoryStore

    from app.agents.graph import build_graph

    return build_graph(checkpointer=MemorySaver(), store=InMemoryStore())
```

TDD:
1. Write `tests/eval/test_harness.py` FIRST — drive a FakeLLM graph that returns a final answer (mirroring `tests/agents/test_graph.py`); the tool-call extraction path is covered separately by the direct `_tools_called` unit test below:

```python
from app.agents.graph import build_graph
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from eval.harness import run_case


def _fake_graph(target="concierge", answer="Ở Tokyo bạn nên thăm **Senso-ji** 🏯"):
    main = FakeLLM(
        structured_responses=[SupervisorIntent(target_agent=target)] * 4,
        responses=[answer] * 4,
    )
    fast = FakeLLM(responses=["OK"] * 4)
    return build_graph(llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore())


def test_run_case_extracts_reply_and_flow():
    res = run_case(_fake_graph(), {"input": "Tokyo có gì chơi?"}, 0)
    assert "Senso-ji" in res.test_case.actual_output
    assert res.current_flow == "concierge"
    assert res.test_case.input == "Tokyo có gì chơi?"


def test_run_case_maps_expected_tools():
    res = run_case(_fake_graph(), {"input": "x", "expected_tools": ["search_hotels"]}, 1)
    assert [t.name for t in res.test_case.expected_tools] == ["search_hotels"]


def test_unique_thread_id_per_index_isolates_history():
    g = _fake_graph()
    a = run_case(g, {"input": "hi"}, 0)
    b = run_case(g, {"input": "again"}, 1)
    # Distinct threads → b did not accumulate a's turn (no cross-case bleed).
    assert a.test_case.actual_output and b.test_case.actual_output


def test_tools_called_extracts_names_from_ai_tool_calls():
    # Direct unit-test of the MIN-46 extraction path (no graph needed).
    from eval.harness import _tools_called

    msg = AIMessage(content="", tool_calls=[{"name": "search_hotels", "args": {}, "id": "1"}])
    assert [t.name for t in _tools_called([msg])] == ["search_hotels"]
    assert _tools_called([AIMessage(content="no tools")]) == []
```

2. Run: `../../.venv/bin/python -m pytest tests/eval/test_harness.py -x` → FAIL then PASS.
Note: if `SupervisorIntent` import path differs, confirm via `grep -n "class SupervisorIntent" app/agents/supervisor.py` (Rule 1 auto-fix if the symbol moved).
  </action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_harness.py -x</verify>
  <done>`run_case` builds an LLMTestCase (reply/tools/expected_tools/current_flow) from a FakeLLM graph; unique thread per case; no network.</done>
</task>
```

### Task 3.1 — Datasets (~15-20 cases) + loader/validator

> Wave 3 (after 2.1): the dataset test cross-checks declared metric names against `eval.metrics_geval.GEVAL_METRICS`, so it must run after Task 2.1 lands.

```xml
<task id="3.1" wave="3">
  <files>apps/api/eval/datasets/intent_min51.json, apps/api/eval/datasets/language_min57.json, apps/api/eval/datasets/tools_min46.json, apps/api/eval/datasets/format_min54.json, apps/api/eval/loader.py, apps/api/tests/eval/test_datasets.py</files>
  <action>
Create four dataset JSON files (~4-6 cases each, ≥15 total) targeting the linked issues, plus a `loader.py` that reads + validates them. Do NOT touch `datasets/routing.json` (owned by the routing smoke).

Case schema (only `input` required): `{"input": str, "expected_flow"?: str, "expected_tools"?: [str], "context"?: [str], "metrics"?: [str], "issue"?: str}`. `metrics` names which GEVAL_METRICS keys apply (defaults handled by the runner).

Example — `datasets/intent_min51.json` (search must NOT trigger booking prompts):

```json
[
  {"input": "Tìm khách sạn ở Đà Nẵng cho 2 người cuối tuần này", "expected_flow": "concierge", "metrics": ["search_vs_booking", "response_language"], "issue": "MIN-51"},
  {"input": "What hotels are available in Hanoi under $50?", "expected_flow": "concierge", "metrics": ["search_vs_booking", "response_language"], "issue": "MIN-51"},
  {"input": "Cho tôi xem các chuyến bay từ TP.HCM đi Tokyo tuần sau", "expected_flow": "concierge", "metrics": ["search_vs_booking"], "issue": "MIN-51"},
  {"input": "Show me flight options SGN to Bangkok next Friday", "expected_flow": "concierge", "metrics": ["search_vs_booking"], "issue": "MIN-51"},
  {"input": "Đặt phòng khách sạn đó giúp tôi", "expected_flow": "booking", "metrics": ["response_language"], "issue": "MIN-51"}
]
```

`language_min57.json` — Vietnamese inputs that must get Vietnamese answers (side-panel language, MIN-57): ~4 VN + 1 EN case, all `"metrics": ["response_language"]`.
`tools_min46.json` — cases with `expected_tools` for `ToolCorrectnessMetric` (e.g. weather → `["get_weather"]`; confirm real tool names via `grep -rn "name=" app/tools/registry.py` — Rule 1 fix names to match). ~4 cases.
`format_min54.json` — info-dense asks that should return bolded/structured answers, `"metrics": ["format_quality"]`. ~4 cases.

`loader.py`:

```python
"""Load + validate offline eval datasets (MIN-58)."""

from __future__ import annotations

import json
from pathlib import Path

_DATASETS = Path(__file__).resolve().parent / "datasets"
_REQUIRED = "input"


def load(name: str) -> list[dict]:
    """Load and validate one dataset file by name (e.g. ``intent_min51.json``)."""
    data = json.loads((_DATASETS / name).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{name}: expected a JSON list")
    for i, case in enumerate(data):
        if _REQUIRED not in case or not isinstance(case[_REQUIRED], str):
            raise ValueError(f"{name}[{i}]: missing required string 'input'")
    return data


def load_all() -> dict[str, list[dict]]:
    """Load every MIN-58 dataset (excludes routing.json — owned by run_eval)."""
    names = ["intent_min51.json", "language_min57.json", "tools_min46.json", "format_min54.json"]
    return {n: load(n) for n in names}
```

TDD:
1. Write `tests/eval/test_datasets.py` FIRST:

```python
from eval.loader import load, load_all
from eval.metrics_geval import GEVAL_METRICS


def test_all_datasets_load_and_validate():
    all_ds = load_all()
    assert set(all_ds) == {"intent_min51.json", "language_min57.json", "tools_min46.json", "format_min54.json"}


def test_total_case_count_at_least_15():
    assert sum(len(v) for v in load_all().values()) >= 15


def test_every_case_has_string_input():
    for cases in load_all().values():
        for c in cases:
            assert isinstance(c["input"], str) and c["input"]


def test_declared_metrics_reference_known_geval_keys():
    for cases in load_all().values():
        for c in cases:
            for m in c.get("metrics", []):
                assert m in GEVAL_METRICS


def test_load_rejects_missing_input(tmp_path, monkeypatch):
    import eval.loader as loader
    bad = tmp_path / "bad.json"
    bad.write_text('[{"nope": 1}]', encoding="utf-8")
    monkeypatch.setattr(loader, "_DATASETS", tmp_path)
    try:
        loader.load("bad.json")
        assert False, "expected ValueError"
    except ValueError:
        pass
```

2. Run: `../../.venv/bin/python -m pytest tests/eval/test_datasets.py -x` → FAIL then PASS.
  </action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_datasets.py -x</verify>
  <done>≥15 validated cases across 4 issue-linked datasets; loader validates required `input`; declared metrics reference real GEVAL_METRICS keys; routing.json untouched.</done>
</task>
```

### Task 4.1 — Keyed runner (skip-gracefully, no-network safe)

```xml
<task id="4.1" wave="4">
  <files>apps/api/eval/run_deepeval.py, apps/api/tests/eval/test_run_deepeval.py</files>
  <action>
Create `eval/run_deepeval.py`: the keyed entry point. It ties loader + harness + metrics via DeepEval's `evaluate()`, but **skips gracefully** (exit 0, notice) when no REAL OpenAI key is present — `apps/api/.env` ships a fake `OPENAI_API_KEY=test`, and CI runs no-network. Keep `eval/run_eval.py` (routing smoke) untouched.

```python
"""Keyed DeepEval runner for the offline eval harness (MIN-58).

Skips gracefully when no real OpenAI judge key is present (the repo ships a fake
`OPENAI_API_KEY=test`, and CI has no network) so this never breaks a no-key run.
`main()` is manual/keyed only; it is NOT wired into CI in this ticket.
"""

from __future__ import annotations

import os
import sys

_PLACEHOLDER_KEYS = {"", "test", "changeme", "placeholder"}


def has_real_openai_key() -> bool:
    """True only when OPENAI_API_KEY is set to a non-placeholder value."""
    return (os.environ.get("OPENAI_API_KEY") or "").strip() not in _PLACEHOLDER_KEYS


def build_test_cases(graph, datasets: dict[str, list[dict]]) -> list:
    """Run every case through the graph → list of LLMTestCase (needs a real graph/key)."""
    from eval.harness import run_case

    cases = []
    for items in datasets.values():
        for i, case in enumerate(items):
            cases.append(run_case(graph, case, i).test_case)
    return cases


def main() -> int:
    """Keyed run: build real graph + judge, evaluate, return process exit code."""
    if not has_real_openai_key():
        print("[eval] SKIP: no real OPENAI_API_KEY (judge) — set one to run DeepEval.")
        return 0

    from deepeval import evaluate

    from eval.harness import build_eval_graph
    from eval.loader import load_all
    from eval.metrics_geval import GEVAL_METRICS, tool_correctness_metric

    graph = build_eval_graph()
    test_cases = build_test_cases(graph, load_all())
    metrics = [f() for f in GEVAL_METRICS.values()] + [tool_correctness_metric()]
    evaluate(test_cases=test_cases, metrics=metrics)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

TDD (all no-network — never call `main()` with a real key in tests):
1. Write `tests/eval/test_run_deepeval.py` FIRST:

```python
import eval.run_deepeval as r


def test_skips_without_real_key(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    assert r.main() == 0
    assert "SKIP" in capsys.readouterr().out


def test_skips_when_key_absent(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert r.main() == 0
    assert "SKIP" in capsys.readouterr().out


def test_has_real_openai_key_detection(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-realish")
    assert r.has_real_openai_key() is True
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    assert r.has_real_openai_key() is False


class _StubGraph:
    """Minimal graph stand-in: .invoke returns a canned result (no network, no cross-test import)."""

    def invoke(self, state, cfg, context=None):
        from langchain_core.messages import AIMessage

        return {"messages": [AIMessage(content="ok")], "current_flow": "concierge"}


def test_build_test_cases_fans_dataset_through_harness():
    cases = r.build_test_cases(_StubGraph(), {"d": [{"input": "a"}, {"input": "b"}]})
    assert len(cases) == 2
    assert [c.input for c in cases] == ["a", "b"]
```

2. Run: `../../.venv/bin/python -m pytest tests/eval/test_run_deepeval.py -x` → FAIL then PASS.
3. Manual smoke (no key): `../../.venv/bin/python -m eval.run_deepeval` → prints SKIP, exit 0.
4. Regression: confirm the routing smoke import path is untouched — `../../.venv/bin/python -c "import eval.run_eval"`.
  </action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/eval/test_run_deepeval.py -x && ../../.venv/bin/python -m eval.run_deepeval</verify>
  <done>Runner skips cleanly with no/placeholder key (exit 0, SKIP notice); `build_test_cases` fans a dataset through the harness; routing smoke import intact.</done>
</task>
```

### Task 4.2 — Full-suite regression gate

```xml
<task id="4.2" wave="4">
  <files>apps/api/tests/eval/</files>
  <action>
Prove the whole eval test package is green and no-network, the routing smoke import is intact, and the runner skips cleanly — with a single `&&`-chained command so ANY failure propagates (exit non-zero). No new files. If `ruff` flags the new modules (F401/unused etc.), fix per Rule 3.

Notes:
- `pytest tests/eval` also collects the PRE-EXISTING `tests/eval/test_eval_smoke.py` — it must stay green (harmless; just don't break it).
- Do NOT execute `eval/run_eval.py`'s `main()` here: it calls `get_llm()` (real provider) and needs a key. Import-only (`import eval.run_eval`) proves the routing smoke module is untouched without network.
- `-m eval.run_deepeval` skips (exit 0) because the shell has no real `OPENAI_API_KEY`.
  </action>
  <verify>cd apps/api && ../../.venv/bin/python -m pytest tests/eval -x && ruff check eval && ../../.venv/bin/python -c "import eval.run_eval" && ../../.venv/bin/python -m eval.run_deepeval</verify>
  <done>All `tests/eval` pass no-network (incl. pre-existing smoke); ruff clean on `eval/`; routing-smoke module imports; run_deepeval skips exit 0.</done>
</task>
```

## 5. Risks

- **Dependency resolution (Deep, Task 1.1):** `deepeval` may pull a transitive tree that bumps fastapi/starlette/pydantic. Mitigation: cap-check gate → **stop & escalate** (separate eval venv/extra or older deepeval pin); never nudge caps.
- **Judge JSON robustness:** OpenAI-native judge avoids the custom-adapter JSON-schema pitfall (deferred). If a later non-OpenAI judge is needed, add a `DeepEvalBaseLLM` adapter honoring the `schema` arg.
- **Symbol drift:** `SupervisorIntent` / real tool names must match — already verified during planning: `SupervisorIntent(target_agent=...)` at `app/agents/supervisor.py:33`; real tool names include `search_hotels` (`app/tools/hotel_tools.py`) and `get_weather` (`app/tools/weather_tools.py`). Re-grep if drifted (Rule 1 auto-fix).
- **`eval` shadows the `eval` builtin:** already the case (`run_eval.py` imports `from eval.metrics`), so the package name is safe here; do not rename.
- **No baseline signal yet:** metric *thresholds* (0.7) are unvalidated until the deferred baseline run — acceptable for the foundation.

## 6. Status Log

- 2026-07-06 — Plan drafted (proposed). Intake lane=normal, confidence=high; research-brief + SUMMARY in spec dir.
- 2026-07-06 — Plan-document-reviewer pass: fixed wave ordering (datasets → wave 3 since its test imports `eval.metrics_geval`), removed unneeded `tests/eval/__init__.py`, replaced fragile cross-test import in the runner test with an inline stub graph, hardened the regression `<verify>` to `&&`-chain (was masking failures) and drop the key-requiring `run_eval.py` execution, added a direct `_tools_called` unit test.
- 2026-07-06 — Wave 1 ✅ Task 1.1 `6918c89` (deepeval 4.0.7 pinned `>=4.0,<5`; caps intact, pip check clean). Deep gate passed, no escalation.
- 2026-07-06 — Wave 2 ✅ Task 2.1 `1eeea9a` (metrics_geval), Task 2.2 `cd5e462` (harness). `tests/eval` = 10 passed no-network, ruff clean. Deviations logged in SUMMARY (deepeval API symbol, eager-key fixture, hook workarounds). Orchestrator metadata `ae3c899`.
- 2026-07-06 — Wave 3 ✅ Task 3.1 `371f9e4` (loader + 4 datasets, 19 cases). `tests/eval` = 15 passed no-network, ruff clean. Rule 3: `assert False`→`pytest.raises` (B011).
- 2026-07-06 — Wave 4 ✅ Task 4.1 `b9d1b07` (run_deepeval runner, skip-gracefully). Task 4.2 regression gate PASS: `tests/eval` = 19 passed no-network, ruff clean, routing-smoke import intact, `run_deepeval` skips exit 0. All 6 tasks done; entering final correctness + intent review.
- 2026-07-06 — `/correctness-review` (sonnet finder, ensemble diversity): 4 findings. Fixed all as Rule 1 — `80bc4cf` (P1 cross-dataset thread_id collision + loader/key/coercion hardening), `c243abf` (re-review caught a Fix-4 regression → block-text extraction). Re-review ✅: all resolved, no open findings. `tests/eval` = 23 passed no-network.
- 2026-07-06 — `/intent-review` (sonnet, blind to PLAN): ✅ **No intent divergence** — 10 intent clauses satisfied, all deferred items correctly absent, no gap/drift/excess. All three oracles (spec/correctness/intent) green. Ready for finishing-a-development-branch.
- 2026-07-06 — shipped via `feat/min-58-chatbot-eval-deepeval` (PR #69, base v3). Targeted suite `tests/eval` = 23 passed no-network.

## 7. Wave Map

| Wave | Tasks | Parallelism | File disjointness |
|------|-------|-------------|-------------------|
| 1 | 1.1 dep spike | single (Deep gate — blocks all) | `requirements-ai.txt` |
| 2 | 2.1 metrics, 2.2 harness | 2 parallel | disjoint: `metrics_geval.py`+test vs `harness.py`+test |
| 3 | 3.1 datasets+loader | single (test imports 2.1's `GEVAL_METRICS`) | `datasets/*.json`+`loader.py`+test |
| 4 | 4.1 runner, 4.2 regression gate | sequential (4.2 after 4.1) | `run_deepeval.py`+test, then full `tests/eval` run |
