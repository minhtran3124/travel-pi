"""Regression: the memory extractor must not capture the assistant's name as the
traveller's name (conv 2239214e — user in English, bot introduced itself as "Tin",
extractor wrongly stored prefs.name = "Tin"). MIN-60 follow-up."""

from app.prompts.registry import registry


def test_extraction_prompt_guards_against_capturing_assistant_name():
    prompt = registry.get("memory_extraction").lower()
    # The guard must name the failure mode explicitly.
    assert "assistant" in prompt
    assert "never capture the assistant" in prompt
