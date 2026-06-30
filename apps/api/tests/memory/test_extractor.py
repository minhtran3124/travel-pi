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
    msgs = [
        HumanMessage(content="What's the weather in Tokyo?"),
        AIMessage(content="Sunny!"),
    ]
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

    json_str = (
        '{"preferences": [], "instructions": [{"key": "style", "text": "be concise"}]}'
    )
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


# --- P2: episodes category (Task 2.2) ---


def test_extract_memories_episodes_populated():
    """FakeLLM returning JSON with episodes → populated ExtractedMemories.episodes."""
    from app.clients.llm import FakeLLM
    from app.memory.extractor import extract_memories

    json_str = (
        '{"preferences": [], "instructions": [],'
        ' "episodes": [{"key": "trip_abc", "text": "Da Nang slow beach trip",'
        ' "city": "Da Nang", "outcome": "approved"}]}'
    )
    llm = FakeLLM(responses=[json_str])
    msgs = [HumanMessage(content="Plan me a Da Nang trip"), AIMessage(content="Done!")]
    result = extract_memories(msgs, llm)
    assert len(result.episodes) == 1
    ep = result.episodes[0]
    assert ep["key"] == "trip_abc"
    assert ep["text"] == "Da Nang slow beach trip"
    assert ep["city"] == "Da Nang"
    assert ep["outcome"] == "approved"


def test_extract_memories_episodes_default_outcome_proposed():
    """An episode item without an explicit outcome defaults to 'proposed'."""
    from app.clients.llm import FakeLLM
    from app.memory.extractor import extract_memories

    json_str = (
        '{"preferences": [], "instructions": [],'
        ' "episodes": [{"key": "trip_x", "text": "Tokyo fast trip", "city": "Tokyo"}]}'
    )
    llm = FakeLLM(responses=[json_str])
    msgs = [HumanMessage(content="Plan Tokyo"), AIMessage(content="Okay")]
    result = extract_memories(msgs, llm)
    assert len(result.episodes) == 1
    assert result.episodes[0]["outcome"] == "proposed"
    assert result.episodes[0]["city"] == "Tokyo"


def test_extract_memories_p1_json_no_episodes_key_backward_compat():
    """P1-era JSON (no 'episodes' key) → episodes == [] (backward compatible)."""
    from app.clients.llm import FakeLLM
    from app.memory.extractor import extract_memories

    json_str = '{"preferences": [{"key": "diet", "text": "vegan"}], "instructions": []}'
    llm = FakeLLM(responses=[json_str])
    msgs = [HumanMessage(content="I'm vegan"), AIMessage(content="Got it")]
    result = extract_memories(msgs, llm)
    assert result.episodes == []
    # P1 fields still parse.
    assert len(result.preferences) == 1
    assert result.preferences[0]["key"] == "diet"


def test_extract_memories_episodes_malformed_items_skipped():
    """Episode items missing 'key' or 'text' are silently skipped."""
    from app.clients.llm import FakeLLM
    from app.memory.extractor import extract_memories

    json_str = (
        '{"preferences": [], "instructions": [],'
        ' "episodes": [{"bad": "item"}, {"key": "trip_ok", "text": "good one",'
        ' "city": "Rome", "outcome": "proposed"}]}'
    )
    llm = FakeLLM(responses=[json_str])
    msgs = [HumanMessage(content="hi"), AIMessage(content="hey")]
    result = extract_memories(msgs, llm)
    assert len(result.episodes) == 1
    assert result.episodes[0]["key"] == "trip_ok"


def test_extract_memories_all_three_categories():
    """All three categories (preferences, instructions, episodes) populate together."""
    from app.clients.llm import FakeLLM
    from app.memory.extractor import extract_memories

    json_str = (
        '{"preferences": [{"key": "diet", "text": "vegetarian"}],'
        ' "instructions": [{"key": "currency", "text": "show EUR"}],'
        ' "episodes": [{"key": "trip_abc", "text": "Rome slow trip",'
        ' "city": "Rome", "outcome": "approved"}]}'
    )
    llm = FakeLLM(responses=[json_str])
    msgs = [
        HumanMessage(content="plan Rome, I'm vegetarian, show EUR"),
        AIMessage(content="Done"),
    ]
    result = extract_memories(msgs, llm)
    assert len(result.preferences) == 1
    assert len(result.instructions) == 1
    assert len(result.episodes) == 1
    assert result.episodes[0]["city"] == "Rome"


def test_extract_memories_empty_arrays_includes_episodes():
    """Empty arrays for all three categories → all empty."""
    from app.clients.llm import FakeLLM
    from app.memory.extractor import extract_memories

    llm = FakeLLM(responses=['{"preferences": [], "instructions": [], "episodes": []}'])
    msgs = [HumanMessage(content="What's the weather?"), AIMessage(content="Sunny")]
    result = extract_memories(msgs, llm)
    assert result.preferences == []
    assert result.instructions == []
    assert result.episodes == []


def test_extract_memories_prompt_v2_has_episodes():
    """memory_extraction v2 prompt mentions the episodes category."""
    from app.prompts.registry import registry

    prompt = registry.get("memory_extraction")
    assert "episodes" in prompt
    assert "preferences" in prompt
    assert "instructions" in prompt
