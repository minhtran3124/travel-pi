"""The specialist really does reach the callback through a live graph run.

Every other test in this area feeds the handler metadata by hand, which proves
the handler's own logic but assumes the part that actually carries the value:
that LangGraph merges a config's ``metadata`` into the child runs it spawns, so
the worker's `{"specialist": ...}` is visible to `on_chat_model_start` inside the
inner sub-graph. If that inheritance ever changed, per-step attribution would go
silently blank and no synthetic test would notice.

So this drives the compiled graph through a real multi-intent turn with the real
handler attached and asserts the specialist arrives on its own.
"""

from app.agents.graph import build_graph
from app.agents.metrics import TurnMetricsHandler
from app.agents.prompt_map import enrich_steps, prompt_versions_snapshot
from app.agents.supervisor import SupervisorIntent
from app.clients.llm import FakeLLM
from app.prompts.registry import registry
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore


def _run_multi_intent_turn() -> TurnMetricsHandler:
    """Drive one real two-specialist turn with the metrics handler attached."""
    main = FakeLLM(
        structured_responses=[
            SupervisorIntent(target_agent="planner", plan=["concierge"])
        ],
        responses=["flights found", "here's what to see", "combined answer"],
    )
    fast = FakeLLM(responses=["OK"])
    graph = build_graph(
        llm=main, fast_llm=fast, checkpointer=MemorySaver(), store=InMemoryStore()
    )
    metrics = TurnMetricsHandler()
    graph.invoke(
        {
            "messages": [HumanMessage(content="flights to Tokyo and things to do")],
            "user_id": "u1",
            "trip_id": None,
        },
        {
            "configurable": {"thread_id": "t-specialist-e2e"},
            "callbacks": [metrics],
        },
    )
    return metrics


def test_worker_steps_carry_their_specialist_from_a_real_run():
    steps = _run_multi_intent_turn().steps()

    worker_steps = [
        s for s in steps if (s.get("ns") or "").startswith("synthesis_worker")
    ]
    assert worker_steps, "the turn produced no synthesis_worker steps"

    specialists = {s["specialist"] for s in worker_steps if s.get("specialist")}
    assert specialists == {"planner", "concierge"}, (
        "the specialist did not reach the callback through the live graph — "
        "LangGraph may no longer merge config metadata into child runs"
    )


def test_worker_llm_steps_attribute_to_the_specialists_prompts():
    steps = _run_multi_intent_turn().steps()
    enriched = enrich_steps(steps, prompt_versions_snapshot(registry))

    named = {
        p["name"]
        for s in enriched
        if s["kind"] == "llm" and (s.get("ns") or "").startswith("synthesis_worker")
        for p in (s.get("prompts") or [])
    }
    # Both specialists' own prompts, plus the style every sub-agent composes in.
    assert {"planner", "concierge", "communication_style"} <= named
