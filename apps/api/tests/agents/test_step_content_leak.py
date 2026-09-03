"""No user content may reach a step row (specs/agent-run-trace-detail §4.3, SC-2).

The intake decision is that a step holds structure and pointers only. This test drives a
distinctive marker through every reachable content source — the tool's ``input_str`` and
``inputs``, the chain's ``outputs`` (graph state, which carries ``messages``), and an
exception message — then asserts the marker survives into no field of any step.
"""

import json
from uuid import uuid4

from app.agents.metrics import TurnMetricsHandler
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, LLMResult

MARKER = "SECRET-MARKER-7f3a"


def _drive_handler() -> TurnMetricsHandler:
    """Push the marker through every content-bearing hook argument."""
    h = TurnMetricsHandler()
    node_id, llm_id, tool_ok, tool_bad, llm_bad = (uuid4() for _ in range(5))
    meta = {"langgraph_node": "concierge", "langgraph_checkpoint_ns": "concierge:t1"}

    # node span — inputs and outputs are graph state
    h.on_chain_start(
        {"name": MARKER},
        {"messages": [HumanMessage(MARKER)]},
        run_id=node_id,
        metadata=meta,
    )

    # a successful LLM call whose content is the marker
    h.on_chat_model_start(
        {},
        [[HumanMessage(MARKER)]],
        run_id=llm_id,
        metadata={**meta, "ls_model_name": "gpt-5-mini"},
    )
    h.on_llm_end(
        LLMResult(
            generations=[
                [
                    ChatGeneration(
                        message=AIMessage(
                            content=MARKER,
                            response_metadata={
                                "model_name": "gpt-5-mini",
                                "finish_reason": "stop",
                                "leaky_extra": MARKER,
                            },
                            usage_metadata={
                                "input_tokens": 5,
                                "output_tokens": 2,
                                "total_tokens": 7,
                            },
                        )
                    )
                ]
            ]
        ),
        run_id=llm_id,
    )

    # a tool call whose arguments are the marker, on both argument channels
    h.on_tool_start(
        {"name": "search_hotels"},
        MARKER,
        run_id=tool_ok,
        metadata=meta,
        inputs={"query": MARKER},
    )
    h.on_tool_end(f"tool output containing {MARKER}", run_id=tool_ok)

    # a failing tool whose exception message quotes user input
    h.on_tool_start(
        {"name": "book_flight"},
        MARKER,
        run_id=tool_bad,
        metadata=meta,
        inputs={"q": MARKER},
    )
    h.on_tool_error(ValueError(f"invalid destination {MARKER}"), run_id=tool_bad)

    # a failing LLM call whose exception message quotes user input
    h.on_chat_model_start(
        {}, [], run_id=llm_bad, metadata={**meta, "ls_model_name": "gpt-5"}
    )
    h.on_llm_error(RuntimeError(f"refused: {MARKER}"), run_id=llm_bad)

    # graph state on the way out
    h.on_chain_end({"messages": [AIMessage(MARKER)], "notes": MARKER}, run_id=node_id)
    return h


def test_marker_appears_in_no_field_of_any_step():
    h = _drive_handler()
    steps = h.steps()
    assert steps, "the handler must have recorded steps for this test to mean anything"

    for step in steps:
        serialised = json.dumps(step, default=str)
        assert MARKER not in serialised, f"marker leaked into step {step}"


def test_marker_appears_in_no_snapshot_field_either():
    h = _drive_handler()
    assert MARKER not in json.dumps(h.snapshot(), default=str)
    assert MARKER not in json.dumps(h.public(), default=str)


def test_meta_is_restricted_to_the_scalar_allowlist():
    """``response_metadata`` carries arbitrary provider keys — only finish_reason is kept."""
    h = _drive_handler()
    llm_steps = [s for s in h.steps() if s["kind"] == "llm"]
    assert llm_steps
    for step in llm_steps:
        assert set(step["meta"]).issubset({"finish_reason"})
    assert llm_steps[0]["meta"] == {"finish_reason": "stop"}


def test_error_type_is_the_class_name_not_the_message():
    h = _drive_handler()
    errored = [s for s in h.steps() if s["status"] == "error"]
    assert {s["error_type"] for s in errored} == {"ValueError", "RuntimeError"}


def test_steps_are_json_serialisable_without_a_default_encoder():
    """A step must contain only JSON primitives — no message objects sneaking through."""
    h = _drive_handler()
    json.dumps(h.steps())


def test_marker_does_not_survive_enrichment_and_persistence(tmp_path):
    """The boundary must hold through the whole write path, not just the handler.

    The handler-level assertions above prove no hook copies content into a step.
    This closes the other half: enrichment adds ``prompts``/``cost_usd`` and the
    repository writes the row, so the marker must be absent from what is actually
    stored and read back — otherwise the guarantee stops at the object boundary.
    """
    from app.agents.prompt_map import enrich_steps
    from app.db.base import Base
    from app.db.engine import get_engine, get_session_factory
    from app.repositories.agent_run import AgentRunRepository

    url = f"sqlite:///{tmp_path / 'leak.db'}"
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    repo = AgentRunRepository(get_session_factory(url))
    repo.start(
        "run-leak",
        user_id="u1",
        conversation_id="c1",
        thread_id="t1",
        trip_id=None,
        channel="chat",
        kind="turn",
        started_at="2026-09-03T00:00:00+00:00",
    )

    enriched = enrich_steps(_drive_handler().steps(), {"supervisor": 9})
    repo.add_steps("run-leak", enriched)

    stored = json.dumps(
        [
            {c.name: getattr(row, c.name) for c in row.__table__.columns}
            for row in repo.steps_for("run-leak")
        ],
        default=str,
    )
    assert MARKER not in stored
