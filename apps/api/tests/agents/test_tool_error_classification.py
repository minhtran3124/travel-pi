"""Sub-agent tool-error classification (#113).

``_tool_error_to_message`` catches every tool failure so an outage cannot 500
``/agent/stream``. It used to also *assert* every failure was "a temporary
upstream problem … try again shortly", so a deterministic failure reached the
traveller as a false outage with unactionable advice. These tests pin one
message class per failure class.

Offline: no LLM, no network, no DB.
"""

from __future__ import annotations

import pytest
from app.agents.subagents._base import _tool_error_to_message
from app.exceptions import ConflictError, NotFoundError, UpstreamError
from app.tools._base import tool_error
from langchain_core.tools import ToolException
from langgraph.prebuilt.tool_node import ToolInvocationError
from pydantic import BaseModel, ValidationError


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


# ---------------------------------------------------------------------------
# Injected-arg failure: the model cannot fix it, and it is NOT an outage
# ---------------------------------------------------------------------------


def test_missing_injected_arg_is_not_reported_as_an_outage():
    """The #113 repro: `get_trip_budget` invoked with {} because state trip_id is None.

    langgraph filters injected args out of the error list, so `filtered_errors`
    is empty — the signal that nothing the model controls was wrong.
    """
    msg = _tool_error_to_message(_invocation_error([]))

    assert "NOT an outage" in msg
    assert "ask the traveller" in msg
    assert "try again shortly" not in msg


def test_missing_injected_arg_tells_the_model_retrying_is_futile():
    msg = _tool_error_to_message(_invocation_error([]))
    assert "retrying will fail identically" in msg


# ---------------------------------------------------------------------------
# Model-fixable bad arguments
# ---------------------------------------------------------------------------


def test_bad_model_arguments_ask_for_a_corrected_call():
    errors = [{"loc": ("city",), "msg": "Field required", "type": "missing"}]
    msg = _tool_error_to_message(_invocation_error(errors))

    assert "arguments are invalid" in msg
    assert "call the tool again" in msg
    assert "try again shortly" not in msg


# ---------------------------------------------------------------------------
# Genuine transient upstream failure — the one case that keeps the old wording
# ---------------------------------------------------------------------------


def test_upstream_error_keeps_the_transient_message():
    cause = UpstreamError("Open-Meteo timed out")
    msg = _tool_error_to_message(_raised(tool_error(cause), cause))

    assert "temporary upstream problem" in msg
    assert "try again shortly" in msg


# ---------------------------------------------------------------------------
# Deterministic domain errors: definite answers, not outages
# ---------------------------------------------------------------------------


def test_not_found_is_a_definite_answer_not_an_outage():
    cause = NotFoundError("Trip 'abc' not found", hint="List the traveller's trips.")
    msg = _tool_error_to_message(_raised(tool_error(cause), cause))

    assert "definite answer" in msg
    assert "do not tell the user to try again later" in msg
    # tool_error keeps detail + hint, which the model needs to recover.
    assert "Trip 'abc' not found" in msg
    assert "List the traveller's trips." in msg


def test_conflict_is_also_a_definite_answer():
    cause = ConflictError("No rooms available for those dates")
    msg = _tool_error_to_message(_raised(tool_error(cause), cause))

    assert "definite answer" in msg
    assert "temporary upstream problem" not in msg


# ---------------------------------------------------------------------------
# Unclassifiable failure: still safe, still no false outage claim
# ---------------------------------------------------------------------------


def test_unknown_failure_does_not_claim_an_outage():
    msg = _tool_error_to_message(RuntimeError("boom"))

    assert "cause is unknown" in msg
    assert "do not claim an outage" in msg
    assert "boom" in msg
