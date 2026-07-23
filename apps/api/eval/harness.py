"""Drive the travel graph and build DeepEval LLMTestCases (MIN-58, MIN-65).

`run_case(graph, case, index)` invokes the compiled graph for one dataset item
and returns an `LLMTestCase` (input, actual_output, tools_called, expected_tools,
context) plus the routed `current_flow`. Dependency-injected so tests drive a
FakeLLM-backed graph with zero network; `build_eval_graph()` builds the real one.

MIN-65 (D9) adds a multi-turn case shape ``{"turns": [...], "new_thread_at": int|null}``,
back-compat with the original single-turn ``{"input": "..."}`` shape. Turns share one
``thread_id`` on the compiled graph (checkpointer accumulates state across them) unless
``new_thread_at`` is set, in which case that turn index opens a NEW ``thread_id`` while
keeping the same ``user_id`` — this models cross-session recall: the checkpointer's
per-thread state resets, but the store (keyed by user_id) is shared across threads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.context import AgentContext
from app.agents.suggestions import suggestions_for_flow
from deepeval.test_case import LLMTestCase, ToolCall
from langchain_core.messages import AIMessage, HumanMessage


@dataclass
class EvalResult:
    """One evaluated case: the DeepEval test case + the routed flow."""

    test_case: LLMTestCase
    current_flow: str | None


def _final_reply(messages: list[Any]) -> str:
    ai = [m for m in messages if isinstance(m, AIMessage)]
    if not ai:
        return ""
    content = ai[-1].content
    if isinstance(content, str):
        return content
    # Provider block-list content (Anthropic/Bedrock): concatenate the text blocks.
    return "".join(b.get("text", "") for b in content if isinstance(b, dict))


def _tools_called(messages: list[Any]) -> list[ToolCall]:
    names: list[str] = []
    for m in messages:
        for tc in getattr(m, "tool_calls", None) or []:
            name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
            if name:
                names.append(name)
    return [ToolCall(name=n) for n in names]


def _invoke_turn(graph: Any, turn: str, user_id: str, thread_id: str) -> dict:
    cfg = {"configurable": {"thread_id": thread_id}}
    return graph.invoke(
        {
            "messages": [HumanMessage(content=turn)],
            "user_id": user_id,
            "trip_id": None,
        },
        cfg,
        context=AgentContext(),
    )


def _build_result(case: dict, out: dict, input_text: str) -> EvalResult:
    messages = out["messages"]
    expected = [ToolCall(name=n) for n in case.get("expected_tools", [])]
    test_case = LLMTestCase(
        input=input_text,
        actual_output=_final_reply(messages),
        tools_called=_tools_called(messages),
        expected_tools=expected,
        context=case.get("context"),
    )
    current_flow = out.get("current_flow")
    # Suggestions aren't graph-generated — call the deterministic rule engine on
    # the final state and carry the result on the test case (MIN-65 D9). The
    # signature is flow-only today; a later task enriches it (trip_facts/profile).
    test_case.metadata = {"suggestions": suggestions_for_flow(current_flow)}
    return EvalResult(test_case=test_case, current_flow=current_flow)


def _run_single_turn(graph: Any, case: dict, index: int) -> EvalResult:
    out = _invoke_turn(graph, case["input"], user_id="eval", thread_id=f"eval-{index}")
    return _build_result(case, out, input_text=case["input"])


def _run_multiturn(graph: Any, case: dict, index: int) -> EvalResult:
    turns: list[str] = case["turns"]
    new_thread_at = case.get("new_thread_at")
    user_id = f"eval-{index}"
    thread_a, thread_b = f"eval-{index}", f"eval-{index}-s2"

    out: dict = {}
    for i, turn in enumerate(turns):
        thread_id = thread_b if new_thread_at is not None and i >= new_thread_at else thread_a
        out = _invoke_turn(graph, turn, user_id=user_id, thread_id=thread_id)

    input_text = "\n".join(f"Turn {i + 1}: {t}" for i, t in enumerate(turns))
    return _build_result(case, out, input_text=input_text)


def run_case(graph: Any, case: dict, index: int) -> EvalResult:
    """Invoke *graph* for one dataset *case* and build its LLMTestCase.

    Supports two case shapes (MIN-65 D9):

    - Single-turn (original, MIN-58): ``{"input": "...", ...}``.
    - Multi-turn: ``{"turns": ["...", "..."], "new_thread_at": int|None, ...}``.
      Turns share one ``thread_id`` unless ``new_thread_at`` is set, in which case
      that turn index onward runs on a fresh ``thread_id`` (same ``user_id``) —
      models cross-session recall via the shared store. ``actual_output`` is
      always the reply from the LAST turn invoked.

    Both shapes accept the same optional fields: ``expected_tools``, ``context``.

    :param graph: A compiled travel graph (real or FakeLLM-backed).
    :param case: Dataset item.
    :param index: Position in the dataset — used to mint unique thread/user ids.
    :return: An :class:`EvalResult`.
    """
    if "turns" in case:
        return _run_multiturn(graph, case, index)
    return _run_single_turn(graph, case, index)


def build_eval_graph() -> Any:
    """Build the REAL travel graph for eval (nodes resolve real providers).

    Uses in-memory checkpointer/store — eval is single-shot per case, no
    persistence needed. Requires a configured provider key at call time.
    """
    from app.agents.graph import build_graph
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.store.memory import InMemoryStore

    return build_graph(checkpointer=MemorySaver(), store=InMemoryStore())
