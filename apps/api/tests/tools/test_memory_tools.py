"""Memory-tools args_schema tests (specs/standardize-tool-args-schema Task 1.2).

Critical edge case: ``user_id``/``store`` are injected via ``InjectedState`` /
``InjectedStore`` and must be excluded from the model-facing ``args_schema``,
while remaining present in the actual function signature so LangGraph still
injects them at call time. We assert schema shape only (no invoke) since a
real invoke needs a running graph/store to perform the injection.
"""

from app.tools.memory_tools import (
    GetUserPreferencesArgs,
    RecallPastTripsArgs,
    SaveUserPreferenceArgs,
    get_user_preferences,
    recall_past_trips,
    save_user_preference,
)


def test_registry_still_builds():
    """Sanity check: adding args_schema to memory tools doesn't break tool wiring."""
    import app.tools.registry  # noqa: F401


def test_save_user_preference_args_schema():
    assert save_user_preference.args_schema is SaveUserPreferenceArgs
    assert save_user_preference.args_schema is not None

    schema = save_user_preference.get_input_schema().model_json_schema()
    props = schema["properties"]
    assert set(props) == {"key", "text"}
    assert schema["required"] == ["key", "text"]
    assert "user_id" not in props
    assert "store" not in props


def test_get_user_preferences_args_schema():
    assert get_user_preferences.args_schema is GetUserPreferencesArgs
    assert get_user_preferences.args_schema is not None

    schema = get_user_preferences.get_input_schema().model_json_schema()
    props = schema["properties"]
    assert set(props) == {"query"}
    assert schema.get("required", []) == []
    assert "user_id" not in props
    assert "store" not in props


def test_recall_past_trips_args_schema():
    assert recall_past_trips.args_schema is RecallPastTripsArgs
    assert recall_past_trips.args_schema is not None

    schema = recall_past_trips.get_input_schema().model_json_schema()
    props = schema["properties"]
    assert set(props) == {"query"}
    assert schema["required"] == ["query"]
    assert "user_id" not in props
    assert "store" not in props


def test_injected_params_remain_in_function_signature():
    """The Annotated[..., InjectedState/InjectedStore] params must still be present
    on the underlying function so LangGraph's ToolNode can inject them at call
    time — only the model-facing args_schema excludes them.
    """
    import inspect

    save_params = inspect.signature(save_user_preference.func).parameters
    assert "user_id" in save_params
    assert "store" in save_params

    get_params = inspect.signature(get_user_preferences.func).parameters
    assert "user_id" in get_params
    assert "store" in get_params

    recall_params = inspect.signature(recall_past_trips.func).parameters
    assert "user_id" in recall_params
    assert "store" in recall_params
