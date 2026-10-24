"""Grader (fast-model) LLM calls made inside a research run must be recorded as
``llm`` steps on the run's metrics handler, not only the main agent's calls.

Regression for #270: Haiku grader calls were absent from ``agent_run_steps``.
"""

from __future__ import annotations

import pytest
from app.agents.metrics import TurnMetricsHandler
from app.clients.llm import FakeLLM
from deepagents.middleware.rubric import GraderResponse

from tests.research.conftest import THREAD_CONFIG, build, context, rubric


def _grader_satisfied() -> dict:
    return {
        "content": "",
        "tool_calls": [
            {
                "name": GraderResponse.__name__,
                "args": {
                    "result": "satisfied",
                    "explanation": "ok",
                    "criteria": [{"name": "c", "passed": True}],
                },
                "id": "grade",
            }
        ],
    }


@pytest.mark.asyncio
async def test_grader_llm_call_is_recorded_as_a_step(store) -> None:
    model = FakeLLM(responses=[{"content": "dossier ready"}])
    grader = FakeLLM(responses=[_grader_satisfied()])
    agent = build(store, llm=model, grader=grader)
    metrics = TurnMetricsHandler()
    config = {**THREAD_CONFIG, "callbacks": [metrics]}

    stream = await agent.astream_events(
        {
            "messages": [{"role": "user", "content": "research"}],
            "rubric": rubric(),
        },
        config,
        version="v3",
        context=context(),
    )
    async for _ in stream:
        pass

    llm_steps = [s for s in metrics.steps() if s["kind"] == "llm"]
    # one main-agent call + one grader call
    assert len(llm_steps) >= 2, llm_steps
