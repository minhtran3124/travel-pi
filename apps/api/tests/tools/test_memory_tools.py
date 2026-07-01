"""Memory-tools schema tests (specs/standardize-tool-args-schema Task 1.2).

Critical edge case: ``user_id``/``store`` are injected via ``InjectedState`` /
``InjectedStore``. An explicit ``args_schema=`` that omits those injected params
breaks LangGraph's ToolNode injection (it derives injection targets from the
tool's schema), so these tools keep an auto-derived schema and attach their
model-facing descriptions inline via ``Annotated[..., Field(description=...)]``.
We therefore assert the MODEL-FACING ``tool_call_schema`` (which excludes the
injected args) rather than ``get_input_schema()`` (which still carries the
un-JSON-able ``BaseStore``). Schema-only (no invoke) since a real invoke needs a
running graph/store to perform injection.
"""

from app.tools.memory_tools import (
    get_user_preferences,
    recall_past_trips,
    save_user_preference,
)


def test_registry_still_builds():
    """Sanity check: the memory tools wire into the registry."""
    import app.tools.registry  # noqa: F401


def _facing(tool):
    """Model-facing schema fields (injected args stripped)."""
    return tool.tool_call_schema.model_fields


def test_save_user_preference_model_facing_schema():
    fields = _facing(save_user_preference)
    assert set(fields) == {"key", "text"}
    assert "user_id" not in fields and "store" not in fields
    assert fields["key"].is_required() and fields["text"].is_required()
    # descriptions carried inline via Annotated[..., Field(description=...)]
    assert fields["key"].description and fields["text"].description


def test_get_user_preferences_model_facing_schema():
    fields = _facing(get_user_preferences)
    assert set(fields) == {"query"}
    assert "user_id" not in fields and "store" not in fields
    assert not fields["query"].is_required()  # optional
    assert fields["query"].description


def test_recall_past_trips_model_facing_schema():
    fields = _facing(recall_past_trips)
    assert set(fields) == {"query"}
    assert "user_id" not in fields and "store" not in fields
    assert fields["query"].is_required()
    assert fields["query"].description


def test_injected_params_remain_in_function_signature():
    """The Annotated[..., InjectedState/InjectedStore] params must still be present
    on the underlying function so LangGraph's ToolNode can inject them at call
    time — only the model-facing schema excludes them.
    """
    import inspect

    for tool in (save_user_preference, get_user_preferences, recall_past_trips):
        params = inspect.signature(tool.func).parameters
        assert "user_id" in params, tool.name
        assert "store" in params, tool.name
