"""Intake probe (gh-193): can a @tool read thread_id from RunnableConfig and the
last HumanMessage id via InjectedState("messages") when run by ToolNode inside a
compiled StateGraph, while both stay hidden from the LLM-visible schema?

Run from apps/api:  ../../.venv/bin/python ../../specs/gh-193-booking-revise-idempotency/evidence/probe_tool_config.py
Exit 0 = both values arrive and only `x` is model-visible.
"""

from typing import Annotated

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import InjectedState, ToolNode

seen: dict = {}


@tool
def probe(
    x: int,
    config: RunnableConfig,
    messages: Annotated[list, InjectedState("messages")] = None,
) -> str:
    """probe tool"""
    seen["thread_id"] = (config or {}).get("configurable", {}).get("thread_id")
    seen["last_human_id"] = next(
        (m.id for m in reversed(messages or []) if isinstance(m, HumanMessage)), None
    )
    return "ok"


assert list(probe.args.keys()) == ["x"], probe.args

g = StateGraph(MessagesState)
g.add_node("tools", ToolNode([probe]))
g.add_edge(START, "tools")
g.add_edge("tools", END)
app = g.compile(checkpointer=MemorySaver())
app.invoke(
    {
        "messages": [
            HumanMessage(content="hi", id="human-1"),
            AIMessage(content="", tool_calls=[{"name": "probe", "args": {"x": 1}, "id": "call-1"}]),
        ]
    },
    config={"configurable": {"thread_id": "t-42"}},
)
assert seen == {"thread_id": "t-42", "last_human_id": "human-1"}, seen
print("ok", seen)
