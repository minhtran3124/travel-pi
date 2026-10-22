"""Sub-agent tool-error classification: the handle_tool_errors hooks must not turn a deterministic or injected-arg failure into a false outage verdict.

Every shared case runs through BOTH hooks (_tool_error_to_message for plain
sub-agents, _tool_error_logic_only for ToolFaultPolicy ones), so a fix to one
cannot silently skip the other. Offline: no LLM, no network, no DB.
"""

from __future__ import annotations

import pytest
from app.agents.retry import _tool_error_logic_only
from app.agents.subagents._base import _tool_error_to_message
from app.exceptions import ConflictError, NotFoundError, UpstreamError
from app.tools._base import tool_error
from langchain_core.tools import ToolException
from langgraph.prebuilt.tool_node import ToolInvocationError
from pydantic import BaseModel, ValidationError

#: Both hooks differ only in what they catch; the wording must not diverge.
HOOKS = [_tool_error_to_message, _tool_error_logic_only]
HOOK_IDS = ["default_hook", "tool_fault_hook"]


class _Args(BaseModel):
    trip_id: str


def _validation_error() -> ValidationError:
    """A real pydantic ValidationError for a missing required field."""
    with pytest.raises(ValidationError) as exc_info:
        _Args()
    return exc_info.value


def _invocation_error(filtered_errors) -> ToolInvocationError:
    return ToolInvocationError(
        tool_name="get_trip_budget",
        source=_validation_error(),
        tool_kwargs={},
        filtered_errors=filtered_errors,
    )


def _raised(exc: ToolException, cause: Exception) -> ToolException:
    """Attach __cause__ the way ``raise tool_error(e) from e`` does."""
    exc.__cause__ = cause
    return exc


@pytest.fixture(params=HOOKS, ids=HOOK_IDS)
def hook(request):
    """Each test runs once per ``handle_tool_errors`` hook."""
    return request.param


# Injected-arg failure: the model cannot fix it, and it is NOT an outage.
def test_missing_injected_arg_is_not_reported_as_an_outage(hook):
    """get_trip_budget invoked with {} because state trip_id is None; langgraph filters injected args out, so empty filtered_errors signals nothing the model controls was wrong."""
    msg = hook(_invocation_error([]))

    assert "NOT an outage" in msg
    assert "ask the traveller" in msg
    assert "try again shortly" not in msg


def test_missing_injected_arg_tells_the_model_retrying_is_futile(hook):
    msg = hook(_invocation_error([]))
    assert "retrying will fail identically" in msg


def test_missing_injected_arg_never_asks_the_model_to_fix_arguments(hook):
    """trip_id is InjectedState, so "check the arguments and try again" advice would invite an impossible retry loop."""
    msg = hook(_invocation_error([]))
    assert "check the arguments" not in msg
    assert "arguments are invalid" not in msg


# Model-fixable bad arguments.
def test_bad_model_arguments_ask_for_a_corrected_call(hook):
    errors = [{"loc": ("city",), "msg": "Field required", "type": "missing"}]
    msg = hook(_invocation_error(errors))

    assert "arguments are invalid" in msg
    assert "call the tool again" in msg
    assert "try again shortly" not in msg


# Genuine transient upstream failure — the one case that keeps the old wording.
def test_upstream_error_keeps_the_transient_message(hook):
    cause = UpstreamError("Open-Meteo timed out")
    msg = hook(_raised(tool_error(cause), cause))

    assert "temporary upstream problem" in msg
    assert "try again shortly" in msg


# Deterministic domain errors: definite answers, not outages.
def test_not_found_is_a_definite_answer_not_an_outage(hook):
    cause = NotFoundError("Trip 'abc' not found", hint="List the traveller's trips.")
    msg = hook(_raised(tool_error(cause), cause))

    assert "definite answer" in msg
    assert "do not tell the user to try again later" in msg
    # tool_error keeps detail + hint, which the model needs to recover.
    assert "Trip 'abc' not found" in msg
    assert "List the traveller's trips." in msg


def test_conflict_is_also_a_definite_answer(hook):
    cause = ConflictError("No rooms available for those dates")
    msg = hook(_raised(tool_error(cause), cause))

    assert "definite answer" in msg
    assert "temporary upstream problem" not in msg


# Tool-authored validation errors: raise ToolException(...) with no `from`.
#: Real causeless raises copied from the tools; no __cause__ to classify by, so the message is all there is.
CAUSELESS = [
    # app/tools/date_tools.py — names the exact correction to make.
    "departure_date 2026-08-15 is in the past (today is 2026-09-01). Do not "
    "guess or invent dates — call the resolve_date tool on the traveller's "
    "original date expression to get the correct concrete date.",
    # app/tools/flight_tools.py — a plain argument rejection.
    "return_date must be on or after departure_date.",
]


@pytest.mark.parametrize("detail", CAUSELESS, ids=["date_tools", "flight_tools"])
def test_causeless_toolexception_is_not_filed_as_unknown(hook, detail):
    """Tools that raise ToolException(...) without `from` have __cause__ None; the classifier must not file them as "cause unknown", which contradicts messages that name the correction to make."""
    msg = hook(ToolException(detail))

    assert "cause is unknown" not in msg
    assert "do not retry blindly" not in msg
    # No false outage.
    assert "try again shortly" not in msg
    assert "temporary upstream problem" not in msg
    # The tool's own words survive; they carry the actual recovery.
    assert detail in msg


def test_causeless_toolexception_allows_self_correction(hook):
    """The model must stay free to fix it and call again.

    This is the class most able to self-correct, so the verdict must not close
    that door the way the injected-arg verdict deliberately does.
    """
    msg = hook(ToolException("return_date must be on or after departure_date."))

    assert "tool's own explanation" in msg
    assert "call the tool again" in msg
    assert "retrying will fail identically" not in msg


# ---------------------------------------------------------------------------
# A bare UpstreamError reaching the catch-all is still transient
# ---------------------------------------------------------------------------


def test_unwrapped_upstream_error_keeps_the_transient_message():
    """Only the broad hook can receive this (see the unknown-failure test).

    `weather_tools`, `routing_tools` and `climate_tools` re-raise `UpstreamError`
    untouched (`raise  # transient — let RetryPolicy retry the node`), so it
    arrives with no __cause__ to classify by. Classifying on `__cause__` alone
    filed a real outage as "cause unknown", breaking the #113 acceptance
    criterion that a genuine upstream failure still reads as transient. Latent
    today — every sub-agent holding an upstream tool has a `ToolFaultPolicy`, so
    the error reaches `RetryPolicy` instead — but the catch-all is the backstop
    for *every* tool error, so it must classify this correctly on its own.
    """
    msg = _tool_error_to_message(UpstreamError("Open-Meteo timed out"))

    assert "temporary upstream problem" in msg
    assert "try again shortly" in msg
    assert "cause is unknown" not in msg
    assert "Open-Meteo timed out" in msg


# ---------------------------------------------------------------------------
# Unclassifiable failure: still safe, still no false outage claim
# ---------------------------------------------------------------------------


def test_unknown_failure_does_not_claim_an_outage():
    """Only the broad hook can receive this.

    `_tool_error_logic_only` is annotated `ToolException`, so ToolNode never
    routes a bare RuntimeError to it — it propagates to the node's RetryPolicy
    instead. Asserting it here would test a call that cannot happen.
    """
    msg = _tool_error_to_message(RuntimeError("boom"))

    assert "cause is unknown" in msg
    assert "do not claim an outage" in msg
    assert "boom" in msg


def test_toolinvocationerror_still_exposes_filtered_errors():
    """Pin the upstream API this classification depends on.

    `filtered_errors` is what separates "the model passed bad arguments" from
    "an injected/runtime arg is missing" — the whole #113 distinction. It does
    not exist before langgraph-prebuilt 1.0.2 (hence the floor in
    requirements-ai.txt), and if a future version drops or renames it the
    classifier would silently fall through to the wrong branch. Fail loudly here
    instead.
    """
    err = _invocation_error([])
    assert hasattr(err, "filtered_errors")
    assert err.filtered_errors == []
    assert _invocation_error(
        [{"loc": ("city",), "msg": "x", "type": "missing"}]
    ).filtered_errors
