"""Node-level tests for the tool-output wrapping seam (specs/rag-tool-output-wrapping, Task 2.1, SC-4).

The seam is the ``"tools"`` node's own callable: ``build_subagent`` registers a
``RunnableLambda`` around an otherwise-unchanged ``ToolNode`` and post-processes
its return value with ``_label_tool_outputs`` (D1/E002). Two earlier seams were
tried and measured broken and must never come back — langgraph's
``wrap_tool_call`` hook (E001, disarms ``TRANSIENT_RETRY`` + ``graceful_fallback``)
and a ``label_tools`` node after ``tools`` (E002, adds a super-step and a
``PROMPTS_FOR_NODE`` gap). The regression that catches E001 lives in
``test_subagent_fault_tolerance.py`` and the one that catches E002 in
``test_trip_guard.py`` / ``test_prompt_map.py``; a focused fault-tolerance check
is repeated here so this file fails first if the seam regresses.

Everything drives a **compiled** graph with ``FakeLLM`` (a bare ``ToolNode``
outside a graph raises ``Missing required config key``). No network, no real LLM.
"""

from __future__ import annotations

import asyncio
import logging

import pytest
from app.agents.retry import (
    GRACEFUL_MSG,
    ToolFaultPolicy,
    _tool_error_logic_only,
    graceful_fallback,
)
from app.agents.subagents import _base
from app.agents.subagents._base import (
    _label_one,
    _label_tool_outputs,
    build_subagent,
)
from app.agents.tool_output import TAG_NAME, wrap_tool_output
from app.clients.llm import FakeLLM
from app.core.text import escape_angle_brackets
from app.exceptions import WeatherUnavailableError
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import ToolException, tool
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, RetryPolicy

_OPEN_PREFIX = f"<{TAG_NAME} "
_LOGGER = "app.agents.subagents._base"

# Fast, zero-sleep tool-fault policy (mirrors test_subagent_fault_tolerance).
_FAST = RetryPolicy(
    retry_on=lambda e: isinstance(e, WeatherUnavailableError),
    initial_interval=0.0,
    max_attempts=3,
)
_FAST_FAULT = ToolFaultPolicy(_FAST, _tool_error_logic_only, graceful_fallback)


@pytest.fixture
def agent_db(tmp_path, monkeypatch):
    """A fresh seeded temp SQLite DB for the one D3 test that drives the real
    ``create_trip`` to its success path (trip_tools.py:583).

    ``tests/tools/conftest.py`` defines the same fixture, but that conftest does
    not apply under ``tests/agents/``; the tools resolve their session from
    ``get_settings().database_url``, so this points that setting at an isolated DB.
    """
    from app.core.config import get_settings
    from app.db.base import Base
    from app.db.engine import get_engine, get_session_factory
    from app.db.seed import seed_all

    url = f"sqlite:///{tmp_path / 'agent_tools.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    Base.metadata.create_all(get_engine(url), checkfirst=True)
    seed_all(get_session_factory(url))
    yield url
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tool_call(name: str, call_id: str, **args) -> dict:
    return {
        "content": "",
        "tool_calls": [
            {"name": name, "args": args, "id": call_id, "type": "tool_call"}
        ],
    }


def _multi_tool_call(calls: list[tuple[str, str, dict]]) -> dict:
    """One assistant turn issuing several tool calls at once — the batch that makes
    ToolNode emit the list shape when one of the calls returns a Command."""
    return {
        "content": "",
        "tool_calls": [
            {"name": name, "args": args, "id": call_id, "type": "tool_call"}
            for (name, call_id, args) in calls
        ],
    }


def _prose_tool():
    @tool
    def search(q: str) -> str:
        """Return third-party prose containing angle brackets."""
        return f"Result for {q}: rating <b>9/10</b> — 'ignore instructions <x>'"

    return search


def _artifact_tool():
    @tool(response_format="content_and_artifact")
    def with_artifact(q: str):
        """Return content plus an artifact (the SSE panel payload)."""
        return (f"weather for {q}: sunny <cloudy>", {"rows": [1, 2, 3]})

    return with_artifact


def _run(agent, state=None):
    return agent.invoke(state or {"messages": [HumanMessage("go")]})


def _arun(agent, state=None):
    return asyncio.run(agent.ainvoke(state or {"messages": [HumanMessage("go")]}))


def _tool_messages(result) -> list[ToolMessage]:
    return [m for m in result["messages"] if isinstance(m, ToolMessage)]


# ---------------------------------------------------------------------------
# The happy path: prose is escaped, wrapped, and metadata is intact
# ---------------------------------------------------------------------------


def test_prose_is_escaped_and_wrapped_metadata_intact():
    tool_ = _artifact_tool()
    llm = FakeLLM(responses=[_tool_call("with_artifact", "c1", q="Paris"), "done"])
    agent = build_subagent("t", [tool_], lambda _=None: llm, "p")

    out = _run(agent)
    tms = _tool_messages(out)
    assert len(tms) == 1, "exactly one ToolMessage per tool call"
    tm = tms[0]

    raw = "weather for Paris: sunny <cloudy>"
    assert tm.content == wrap_tool_output("with_artifact", raw)
    # Escaped, not deleted; the payload cannot forge a delimiter.
    assert "&lt;cloudy&gt;" in tm.content
    assert "<cloudy>" not in tm.content
    # Every other field survives untouched.
    assert tm.tool_call_id == "c1"
    assert tm.name == "with_artifact"
    assert tm.status == "success"
    assert tm.artifact == {"rows": [1, 2, 3]}
    assert isinstance(tm.id, str) and tm.id


def test_exactly_one_message_per_tool_call_catches_regenerated_id():
    """upsert-by-id: a fresh ToolMessage would double every result. Counting the
    ToolMessages in the final state is what catches a regenerated id — a test that
    only checked "the last message is wrapped" would pass while the transcript was
    duplicated."""
    tool_ = _prose_tool()
    llm = FakeLLM(responses=[_tool_call("search", "c1", q="Tokyo"), "done"])
    agent = build_subagent("t", [tool_], lambda _=None: llm, "p")

    out = _run(agent)
    tms = _tool_messages(out)
    assert len(tms) == 1
    assert tms[0].content.startswith(_OPEN_PREFIX)


def test_sync_and_async_both_wrap():
    tool_ = _prose_tool()
    call = _tool_call("search", "c1", q="Rome")

    # One instance per agent — resolve_model(None) is called every assistant turn,
    # so a fresh FakeLLM each call would reset to index 0 and loop forever.
    sync_llm = FakeLLM(responses=[call, "done"])
    async_llm = FakeLLM(responses=[call, "done"])
    sync_agent = build_subagent("t", [tool_], lambda _=None: sync_llm, "p")
    async_agent = build_subagent("t", [tool_], lambda _=None: async_llm, "p")

    sync_tm = _tool_messages(_run(sync_agent))[0]
    async_tm = _tool_messages(_arun(async_agent))[0]

    assert sync_tm.content.startswith(_OPEN_PREFIX)
    assert async_tm.content.startswith(_OPEN_PREFIX)
    assert sync_tm.content == async_tm.content


# ---------------------------------------------------------------------------
# First-party messages (D3) are left untouched
# ---------------------------------------------------------------------------


def test_error_result_is_not_wrapped():
    @tool
    def boom(q: str) -> str:
        """Always fails with a logic error."""
        raise ToolException("nope")

    llm = FakeLLM(responses=[_tool_call("boom", "c1", q="x"), "done"])
    agent = build_subagent("t", [boom], lambda _=None: llm, "p")

    tm = _tool_messages(_run(agent))[0]
    assert tm.status == "error"
    assert not tm.content.startswith(_OPEN_PREFIX)
    assert TAG_NAME not in tm.content


def test_needs_clarification_command_reaches_assistant_untouched():
    """clarification_tools.py:55 — a success ToolMessage inside a Command.update.
    Through this seam it arrives as a Command entry in the list shape and is left
    untouched by the Command-vs-ToolMessage branch."""
    llm = FakeLLM(responses=[_tool_call("needs_clarification", "c1"), "which date?"])
    # needs_clarification is appended to every sub-agent by build_subagent.
    agent = build_subagent("t", [], lambda _=None: llm, "p")

    out = _run(agent)
    assert out["awaiting_user"] is True
    tm = _tool_messages(out)[0]
    assert tm.tool_call_id == "c1"
    assert not tm.content.startswith(_OPEN_PREFIX)
    assert "remaining queued work" in tm.content


def test_d3_command_tools_untouched_in_a_batch_with_an_ordinary_tool(agent_db):
    """D3 corrected, by identity: the two success-ToolMessage-in-a-Command sites —
    ``needs_clarification`` (clarification_tools.py:55) and ``create_trip``
    (trip_tools.py:583) — arrive as Command entries in the list shape ToolNode
    returns when any call yields a Command, and stay unwrapped, while an ordinary
    ToolMessage in the same list is wrapped. Asserted against the real tools, so a
    future change to a bare ToolMessage return fails here."""
    from app.tools.clarification_tools import needs_clarification
    from app.tools.trip_tools import create_trip

    clar_cmd = needs_clarification.invoke(
        {"type": "tool_call", "id": "c1", "name": "needs_clarification", "args": {}}
    )
    trip_cmd = create_trip.invoke(
        {
            "type": "tool_call",
            "id": "c2",
            "name": "create_trip",
            "args": {"title": "Da Nang weekend", "city": "Da Nang", "user_id": "u1"},
        }
    )
    assert isinstance(clar_cmd, Command)
    assert isinstance(trip_cmd, Command)
    # Precondition: both build a SUCCESS ToolMessage (no status="error"), which is
    # exactly why the status skip cannot be what protects them — the Command shape is.
    clar_inner = clar_cmd.update["messages"][0]
    trip_inner = trip_cmd.update["messages"][0]
    assert clar_inner.status != "error"
    assert trip_inner.status != "error"

    ordinary = ToolMessage(content="plain <x>", tool_call_id="c3", name="search")
    # The REAL list shape ToolNode produces when at least one call returned a
    # Command AND the node was invoked with a state dict (input_type == "dict", as
    # this graph always does): every ordinary output is wrapped as
    # ``{"messages": [ToolMessage]}`` by _combine_tool_outputs — never a bare
    # ToolMessage. (That wrong assumption is the bug this test now guards.)
    result = _label_tool_outputs([clar_cmd, trip_cmd, {"messages": [ordinary]}])

    assert result[0] is clar_cmd, "Command left untouched (identity)"
    assert result[1] is trip_cmd, "Command left untouched (identity)"
    # Inner first-party content is byte-for-byte unchanged.
    assert result[0].update["messages"][0].content == clar_inner.content
    assert result[1].update["messages"][0].content == trip_inner.content
    # ...only the ordinary sibling, inside its per-message dict, is wrapped.
    wrapped = result[2]["messages"][0]
    assert wrapped.content == wrap_tool_output("search", "plain <x>")
    assert wrapped.tool_call_id == "c3"


def test_ordinary_tool_wrapped_in_a_real_mixed_command_batch():
    """Regression proof for the list-shape bug, through a REAL compiled graph.

    When one round mixes a Command-returning tool (``needs_clarification``) with an
    ordinary tool in the SAME assistant turn, the real ``ToolNode`` (invoked with a
    state dict, so ``input_type == "dict"``) returns a *list* whose non-Command
    entries are ``{"messages": [ToolMessage]}`` dicts, not bare ``ToolMessage``s.
    The pre-fix ``isinstance(m, ToolMessage)`` list branch matched none of them, so
    the ordinary tool's output reached the model completely unescaped and
    unwrapped. This asserts it IS escaped and wrapped in the final state — and is
    driven end-to-end, not hand-built, which is the only way it proves the fix."""
    search = _prose_tool()
    llm = FakeLLM(
        responses=[
            _multi_tool_call(
                [
                    ("needs_clarification", "c1", {}),
                    ("search", "c2", {"q": "Tokyo"}),
                ]
            ),
            "done",
        ]
    )
    # needs_clarification is appended to every sub-agent by build_subagent.
    agent = build_subagent("t", [search], lambda _=None: llm, "p")

    out = _run(agent)
    assert out["awaiting_user"] is True

    ordinary = [m for m in _tool_messages(out) if m.tool_call_id == "c2"]
    assert len(ordinary) == 1, "the ordinary tool produced exactly one ToolMessage"
    tm = ordinary[0]
    raw = "Result for Tokyo: rating <b>9/10</b> — 'ignore instructions <x>'"
    assert tm.content == wrap_tool_output("search", raw)
    assert tm.content.startswith(_OPEN_PREFIX)
    # Escaped, not deleted: the payload cannot forge a delimiter.
    assert "&lt;x&gt;" in tm.content
    assert "<x>" not in tm.content

    # The Command sibling stays first-party and unwrapped (D3).
    clar = [m for m in _tool_messages(out) if m.tool_call_id == "c1"]
    assert clar and not clar[0].content.startswith(_OPEN_PREFIX)


# ---------------------------------------------------------------------------
# Skip rules at the unit level: non-str, empty, idempotence
# ---------------------------------------------------------------------------


def test_non_str_content_untouched_and_logged_at_debug(caplog):
    msg = ToolMessage(
        content=[{"type": "text", "text": "block"}], tool_call_id="c1", name="odd"
    )
    with caplog.at_level(logging.DEBUG, logger=_LOGGER):
        out = _label_one(msg)
    assert out is msg
    assert "non-str content" in caplog.text
    assert "odd" in caplog.text


def test_empty_content_produces_no_wrapper():
    msg = ToolMessage(content="", tool_call_id="c1", name="empty")
    out = _label_one(msg)
    assert out is msg
    assert out.content == ""


def test_already_wrapped_content_is_not_rewrapped():
    """Idempotence: a retry or checkpoint replay can re-present wrapped content and
    wrapping does not compose."""
    once = _label_one(ToolMessage(content="hello <x>", tool_call_id="c1", name="s"))
    assert once.content == wrap_tool_output("s", "hello <x>")
    # Feeding the already-wrapped content back must be a no-op.
    twice = _label_one(ToolMessage(content=once.content, tool_call_id="c1", name="s"))
    assert twice.content == once.content
    assert twice.content.count(f"</{TAG_NAME}>") == 1


def test_label_tool_outputs_dict_shape_idempotent():
    tm = ToolMessage(content="a <b> c", tool_call_id="c1", name="s")
    once = _label_tool_outputs({"messages": [tm]})
    twice = _label_tool_outputs(once)
    assert once["messages"][0].content == wrap_tool_output("s", "a <b> c")
    assert twice["messages"][0].content == once["messages"][0].content


def test_transform_failure_delivers_message_unchanged_and_warns(monkeypatch, caplog):
    """A transform that raises on one message delivers it unchanged and warns —
    never dropped, since a missing tool_call_id makes the provider reject the next
    assistant turn."""

    def _boom(name, text):
        raise RuntimeError("wrap exploded")

    monkeypatch.setattr(_base, "wrap_tool_output", _boom)
    msg = ToolMessage(content="payload", tool_call_id="c1", name="s")
    with caplog.at_level(logging.WARNING, logger=_LOGGER):
        out = _label_one(msg)
    assert out is msg
    assert "wrapping failed" in caplog.text


def test_label_tool_outputs_passes_through_unknown_shapes():
    sentinel = object()
    assert _label_tool_outputs(sentinel) is sentinel


# ---------------------------------------------------------------------------
# Both ToolNode construction branches label, with policies still attached
# ---------------------------------------------------------------------------


def test_no_fault_branch_wraps_and_has_no_policies():
    tool_ = _prose_tool()
    llm = FakeLLM(responses=[_tool_call("search", "c1", q="x"), "done"])
    agent = build_subagent("t", [tool_], lambda _=None: llm, "p")

    node = agent.nodes["tools"]
    assert isinstance(node.bound, RunnableLambda)
    assert not isinstance(node.bound, ToolNode)
    assert node.retry_policy is None
    assert node.error_handler_node is None
    assert _tool_messages(_run(agent))[0].content.startswith(_OPEN_PREFIX)


def test_fault_branch_wraps_and_keeps_retry_and_error_handler():
    tool_ = _prose_tool()
    llm = FakeLLM(responses=[_tool_call("search", "c1", q="x"), "done"])
    agent = build_subagent(
        "t", [tool_], lambda _=None: llm, "p", tool_fault=_FAST_FAULT
    )

    node = agent.nodes["tools"]
    assert isinstance(node.bound, RunnableLambda)
    assert not isinstance(node.bound, ToolNode)
    # retry_policy is stored as a tuple on the PregelNode; the policy must be ours.
    assert node.retry_policy and _FAST in node.retry_policy
    assert node.error_handler_node is not None
    assert _tool_messages(_run(agent))[0].content.startswith(_OPEN_PREFIX)


# ---------------------------------------------------------------------------
# The seam is pinned: a revert to a bare ToolNode fails here (E002)
# ---------------------------------------------------------------------------


def test_tools_node_runnable_is_the_wrapping_runnable_lambda_not_a_bare_toolnode():
    tool_ = _prose_tool()
    agent = build_subagent("t", [tool_], lambda _=None: FakeLLM(responses=["x"]), "p")
    node = agent.nodes["tools"]
    assert isinstance(node.bound, RunnableLambda), (
        "the 'tools' node must be the wrapping RunnableLambda; a bare ToolNode "
        "would silently disable wrapping"
    )
    assert not isinstance(node.bound, ToolNode)
    # No node was added by the seam (E002 guard, local): no label_tools key.
    assert "label_tools" not in agent.nodes


# ---------------------------------------------------------------------------
# Fault tolerance still works with the wrapper in place (E001 guard, local)
# ---------------------------------------------------------------------------


class _FlakyWeather:
    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.calls = 0

    def make(self):
        @tool
        def flaky_weather(city: str) -> str:
            """Get the weather for a city."""
            self.calls += 1
            if self.calls <= self.fail_times:
                raise WeatherUnavailableError("open-meteo down")
            return f"Weather in {city}: sunny <clear>"

        return flaky_weather


def _weather_llm():
    return FakeLLM(
        responses=[_tool_call("flaky_weather", "c1", city="Paris"), "Told the user."]
    )


def test_flaky_tool_still_retries_three_times_and_then_wraps():
    """E001 guard: the wrapper never intercepts execution, so a transient fault
    propagates and RetryPolicy still retries; the eventual success is wrapped."""
    flaky = _FlakyWeather(fail_times=2)
    llm = _weather_llm()
    agent = build_subagent(
        "t", [flaky.make()], lambda _=None: llm, "p", tool_fault=_FAST_FAULT
    )
    out = _run(agent)
    assert flaky.calls == 3  # 1 initial + 2 retries
    tm = _tool_messages(out)[0]
    assert tm.content == wrap_tool_output(
        "flaky_weather", "Weather in Paris: sunny <clear>"
    )


def test_graceful_fallback_after_exhaustion_is_unwrapped():
    """E001 guard: an exhausted retry degrades through graceful_fallback, whose
    status='error' message must reach the assistant unwrapped (D3)."""
    flaky = _FlakyWeather(fail_times=99)  # never succeeds
    llm = _weather_llm()
    agent = build_subagent(
        "t", [flaky.make()], lambda _=None: llm, "p", tool_fault=_FAST_FAULT
    )
    out = _run(agent)
    assert flaky.calls == 3  # exhausted after max_attempts
    graceful = [m for m in _tool_messages(out) if m.content == GRACEFUL_MSG]
    assert graceful and graceful[0].tool_call_id == "c1"
    assert not graceful[0].content.startswith(_OPEN_PREFIX)


# ---------------------------------------------------------------------------
# Escaping is lossless (a traveller's own prose survives)
# ---------------------------------------------------------------------------


def test_wrapping_is_lossless_under_strip():
    raw = "dinner <7pm, price & value, [possible-duplicate:z9]"
    msg = ToolMessage(content=raw, tool_call_id="c1", name="notes")
    wrapped = _label_one(msg).content
    assert wrapped == wrap_tool_output("notes", raw)
    # Only escaping changed the body; nothing was deleted.
    from app.agents.tool_output import strip_wrappers

    assert strip_wrappers(wrapped) == escape_angle_brackets(raw)
