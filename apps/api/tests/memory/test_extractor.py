"""Task 1.4 — Memory extractor (specs/agent-memory-layers)."""

from langchain_core.messages import AIMessage, HumanMessage


def test_extract_memories_valid_json_populated():
    """FakeLLM returning valid JSON → populated ExtractedMemories."""
    from app.clients.llm import FakeLLM
    from app.memory.extractor import extract_memories

    json_str = (
        '{"preferences": [{"key": "diet", "text": "vegetarian"}],'
        '"instructions": [{"key": "currency", "text": "show EUR"}]}'
    )
    llm = FakeLLM(responses=[json_str])
    msgs = [
        HumanMessage(content="I'm vegetarian and always want EUR prices"),
        AIMessage(content="Noted!"),
    ]
    result = extract_memories(msgs, llm)
    assert len(result.preferences) == 1
    assert result.preferences[0] == {"key": "diet", "text": "vegetarian"}
    assert len(result.instructions) == 1
    assert result.instructions[0] == {"key": "currency", "text": "show EUR"}


def test_extract_memories_empty_arrays():
    """FakeLLM returning empty arrays → empty result."""
    from app.clients.llm import FakeLLM
    from app.memory.extractor import extract_memories

    llm = FakeLLM(responses=['{"preferences": [], "instructions": []}'])
    msgs = [HumanMessage(content="What's the weather in Tokyo?"), AIMessage(content="Sunny!")]
    result = extract_memories(msgs, llm)
    assert result.preferences == []
    assert result.instructions == []


def test_extract_memories_malformed_json_empty_result():
    """Garbage/non-JSON content → empty ExtractedMemories (no exception)."""
    from app.clients.llm import FakeLLM
    from app.memory.extractor import extract_memories

    llm = FakeLLM(responses=["not valid json at all"])
    msgs = [HumanMessage(content="hi"), AIMessage(content="hey")]
    result = extract_memories(msgs, llm)
    assert result.preferences == []
    assert result.instructions == []


def test_extract_memories_empty_string_content():
    """Empty string response → empty result, no exception."""
    from app.clients.llm import FakeLLM
    from app.memory.extractor import extract_memories

    llm = FakeLLM(responses=[""])
    msgs = [HumanMessage(content="hi"), AIMessage(content="hey")]
    result = extract_memories(msgs, llm)
    assert result.preferences == []
    assert result.instructions == []


def test_extract_memories_wrong_shape_ignored():
    """JSON that isn't a dict → empty result (no exception)."""
    from app.clients.llm import FakeLLM
    from app.memory.extractor import extract_memories

    llm = FakeLLM(responses=['["wrong", "shape"]'])
    msgs = [HumanMessage(content="hi"), AIMessage(content="hey")]
    result = extract_memories(msgs, llm)
    assert result.preferences == []
    assert result.instructions == []


def test_extract_memories_skips_malformed_items():
    """Items missing 'key' or 'text' are silently skipped."""
    from app.clients.llm import FakeLLM
    from app.memory.extractor import extract_memories

    json_str = (
        '{"preferences": [{"bad": "item"}, {"key": "diet", "text": "vegan"}],'
        '"instructions": []}'
    )
    llm = FakeLLM(responses=[json_str])
    msgs = [HumanMessage(content="I'm vegan"), AIMessage(content="Got it!")]
    result = extract_memories(msgs, llm)
    assert len(result.preferences) == 1
    assert result.preferences[0] == {"key": "diet", "text": "vegan"}


def test_extract_memories_only_preferences():
    """Only preferences populated; instructions empty."""
    from app.clients.llm import FakeLLM
    from app.memory.extractor import extract_memories

    json_str = '{"preferences": [{"key": "airline", "text": "prefers ANA"}], "instructions": []}'
    llm = FakeLLM(responses=[json_str])
    msgs = [HumanMessage(content="I like ANA"), AIMessage(content="Okay!")]
    result = extract_memories(msgs, llm)
    assert len(result.preferences) == 1
    assert result.instructions == []


def test_extract_memories_only_instructions():
    """Only instructions populated; preferences empty."""
    from app.clients.llm import FakeLLM
    from app.memory.extractor import extract_memories

    json_str = '{"preferences": [], "instructions": [{"key": "style", "text": "be concise"}]}'
    llm = FakeLLM(responses=[json_str])
    msgs = [HumanMessage(content="Keep it short"), AIMessage(content="Will do!")]
    result = extract_memories(msgs, llm)
    assert len(result.instructions) == 1
    assert result.preferences == []


def test_extract_memories_prompt_registered():
    """memory_extraction prompt is registered and loadable."""
    from app.prompts.registry import registry

    prompt = registry.get("memory_extraction")
    assert "preferences" in prompt
    assert "instructions" in prompt
    assert "JSON" in prompt
