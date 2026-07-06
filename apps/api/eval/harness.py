"""Drive the travel graph and build DeepEval LLMTestCases (MIN-58).

`run_case(graph, case, index)` invokes the compiled graph for one dataset item
and returns an `LLMTestCase` (input, actual_output, tools_called, expected_tools,
context) plus the routed `current_flow`. Dependency-injected so tests drive a
FakeLLM-backed graph with zero network; `build_eval_graph()` builds the real one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.context import AgentContext
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
        {
            "messages": [HumanMessage(content=case["input"])],
            "user_id": "eval",
            "trip_id": None,
        },
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
    from app.agents.graph import build_graph
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.store.memory import InMemoryStore

    return build_graph(checkpointer=MemorySaver(), store=InMemoryStore())
