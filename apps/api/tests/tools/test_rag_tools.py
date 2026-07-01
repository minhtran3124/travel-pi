"""Tests for search_destination_knowledge's args_schema (specs/standardize-tool-args-schema Task 3.3)."""

from app.tools.rag_tools import (
    SearchDestinationKnowledgeArgs,
    search_destination_knowledge,
)


def test_search_destination_knowledge_has_hand_authored_args_schema():
    assert search_destination_knowledge.args_schema is SearchDestinationKnowledgeArgs
    assert search_destination_knowledge.args_schema.__module__.startswith("app.tools")


def test_search_destination_knowledge_schema_required_optional():
    schema = search_destination_knowledge.get_input_schema().model_json_schema()
    assert schema["required"] == ["query"]
    assert "city" in schema["properties"]
    assert "city" not in schema.get("required", [])
