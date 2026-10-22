"""Sub-agent fault-tolerance wiring."""

from app.agents.retry import ToolFaultPolicy, _tool_error_logic_only, graceful_fallback
from app.agents.subagents._base import build_subagent
from app.clients.llm import FakeLLM
from app.exceptions import WeatherUnavailableError
from langchain_core.messages import HumanMessage
from langchain_core.tools import ToolException, tool
from langgraph.prebuilt.tool_node import _infer_handled_types
from langgraph.types import RetryPolicy
from pydantic import PrivateAttr

# Fast, zero-sleep policy for tests.
_FAST = RetryPolicy(
    retry_on=lambda e: isinstance(e, WeatherUnavailableError),
    initial_interval=0.0,
    max_attempts=3,
)
_FAST_FAULT = ToolFaultPolicy(_FAST, _tool_error_logic_only, graceful_fallback)


class FlakyLLM(FakeLLM):
    fail_times: int = 1
    _calls: int = PrivateAttr(default=0)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self._calls += 1
        if self._calls <= self.fail_times:
            err = RuntimeError("rate limited")
            err.status_code = 429
            raise err
        return super()._generate(messages, stop, run_manager, **kwargs)


def test_narrowed_handler_only_catches_toolexception():
    assert _infer_handled_types(_tool_error_logic_only) == (ToolException,)


def test_assistant_node_retries_transient_llm_error():
    flaky = FlakyLLM(fail_times=1, responses=["Paris is sunny"])
    sub = build_subagent("t", [], lambda _=None: flaky, "prompt")
    result = sub.invoke({"messages": [HumanMessage("weather in Paris")]})
    assert flaky._calls == 2  # failed once, retried, succeeded
    assert result["messages"][-1].content == "Paris is sunny"


def _flaky_weather_tool(counter: dict, fail_times: int):
    @tool
    def flaky_weather(city: str) -> str:
        """Get the weather for a city."""
        counter["n"] += 1
        if counter["n"] <= fail_times:
            raise WeatherUnavailableError("open-meteo down")
        return f"Weather in {city}: sunny"

    return flaky_weather


def _tool_calling_llm():
    return FakeLLM(
        responses=[
            {
                "content": "",
                "tool_calls": [
                    {
                        "name": "flaky_weather",
                        "args": {"city": "Paris"},
                        "id": "c1",
                        "type": "tool_call",
                    }
                ],
            },
            "Done — told the user.",
        ]
    )


def test_tools_node_retries_then_succeeds():
    counter = {"n": 0}
    tool_ = _flaky_weather_tool(counter, fail_times=2)  # fail 2, succeed on attempt 3
    llm = (
        _tool_calling_llm()
    )  # one instance: resolve_model is called per assistant turn
    sub = build_subagent(
        "t",
        [tool_],
        lambda _=None: llm,
        "prompt",
        tool_fault=_FAST_FAULT,
    )
    result = sub.invoke({"messages": [HumanMessage("weather in Paris")]})
    assert counter["n"] == 3  # 1 initial + 2 retries (max_attempts=3)
    assert result["messages"][-1].content == "Done — told the user."


def test_tools_node_graceful_after_exhaustion():
    from app.agents.retry import GRACEFUL_MSG

    counter = {"n": 0}
    tool_ = _flaky_weather_tool(counter, fail_times=99)  # always fails
    llm = (
        _tool_calling_llm()
    )  # one instance: resolve_model is called per assistant turn
    sub = build_subagent(
        "t",
        [tool_],
        lambda _=None: llm,
        "prompt",
        tool_fault=_FAST_FAULT,
    )
    result = sub.invoke({"messages": [HumanMessage("weather in Paris")]})
    assert counter["n"] == 3  # exhausted after max_attempts
    graceful = [
        m for m in result["messages"] if getattr(m, "content", None) == GRACEFUL_MSG
    ]
    assert (
        graceful and graceful[0].tool_call_id == "c1"
    )  # no 500; graceful ToolMessage emitted
