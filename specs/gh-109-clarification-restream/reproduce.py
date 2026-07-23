"""Offline deterministic reproduction for GitHub issue #109."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from langchain_core.messages import HumanMessage  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.store.memory import InMemoryStore  # noqa: E402

from app.agents.graph import build_graph  # noqa: E402
from app.agents.supervisor import SupervisorIntent  # noqa: E402
from app.clients.llm import FakeLLM  # noqa: E402
from app.streaming.mapper import stream_agent_events  # noqa: E402


async def main() -> None:
    prefix = (
        "I can do that — I just need one exact date to anchor everything.\n\n"
        "You said end of this month is too broad."
    )
    complete = f"{prefix}\n\nWhat exact departure date should I use?"
    llm = FakeLLM(
        structured_responses=[
            SupervisorIntent(
                target_agent="planner",
                plan=["concierge", "budget"],
            )
        ],
        responses=[
            {
                "content": prefix,
                "tool_calls": [
                    {
                        "name": "needs_clarification",
                        "args": {},
                        "id": "call-clarify-1",
                    }
                ],
            },
            complete,
            "NEVER RUN",
        ],
    )
    graph = build_graph(
        llm=llm,
        fast_llm=FakeLLM(responses=["OK"]),
        checkpointer=MemorySaver(),
        store=InMemoryStore(),
    )
    cfg = {"configurable": {"thread_id": "issue-109-probe"}}
    stream_input = {
        "messages": [HumanMessage(content="Plan Tokyo at end of month")],
        "user_id": "u1",
        "trip_id": None,
    }

    async for event in stream_agent_events(
        graph,
        stream_input,
        cfg=cfg,
        conversation_id="c1",
    ):
        if event.event in {"token", "reset", "tool_call", "tool_result", "done"}:
            print(event.event, json.loads(event.data))


if __name__ == "__main__":
    asyncio.run(main())
