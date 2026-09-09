"""Content-level pin for the supervisor prompt (v12 tool-decided fan-out).

GH-173: v11 §3 enumerated the *planner's* tools by name but stated the fan-out
exception as a judgment call, so the model collapsed "plan everything … local
tips …" to planner-alone and silently dropped the traveller's question. v12
states both halves in tools. These tests pin that shape.

The #149 guard matters as much as the fix: #149 is the OPPOSITE bug on the same
decision (flights + weather fanning out when the planner owns both tools), so
``test_supervisor_prompt_keeps_planner_owned_not_a_trigger`` exists to stop a
future edit from turning the fan-out rule into blanket fan-out pressure.

Assertions are on the rule's substance, not on whole paragraphs — a
full-paragraph pin would break on the next legitimate bump. The prompt is
hard-wrapped, so every check normalizes whitespace first.
"""

from app.agents.supervisor import SupervisorIntent
from app.prompts.registry import registry


def _normalized() -> str:
    return " ".join(registry.get("supervisor").split())


def test_supervisor_prompt_names_concierge_only_tools():
    # The fan-out trigger is a tool list the model can check, not a judgment
    # call. All three tools are concierge-only in app/tools/registry.py.
    text = _normalized()
    for tool in ("get_local_tips", "get_visa", "search_travel_knowledge"):
        assert tool in text, f"supervisor prompt no longer names {tool}"


def test_supervisor_prompt_keeps_planner_owned_not_a_trigger():
    # The #149 guard: weather and places are planner-owned, so they must NOT
    # read as a reason to add a second worker. Asserted on substance, not on a
    # verbatim sentence — a reword that keeps the rule must keep passing.
    text = _normalized()
    assert "get_weather" in text
    assert "search_places" in text
    # Naming the tools is not enough — §3's planner-ownership sentence already
    # does that. The guard is the DENIAL that they justify a second worker, so
    # assert a clause carrying that denial and tying it to weather/places.
    # These two phrasings are the accepted vocabulary; reword the test with the
    # prompt if the rule is ever restated differently.
    denials = [
        clause
        for clause in text.replace(". ", "|").replace(", ", "|").split("|")
        if "second worker" in clause or "reason to fan out" in clause
    ]
    assert denials, "the prompt no longer denies that a second worker is needed"
    assert any(
        "weather" in clause.lower() or "places" in clause.lower()
        for clause in denials
    ), "the fan-out denial is no longer tied to weather/places (the #149 guard)"


def test_supervisor_prompt_has_contrastive_pair():
    # The teaching signal is the CONTRAST: the same request with and without
    # local tips, adjacent in the few-shot block. A lone fan-out example would
    # only raise fan-out pressure (the #149 risk).
    examples = [
        line
        for line in registry.get("supervisor").splitlines()
        if line.startswith("- \"plan my weekend")
    ]
    assert len(examples) == 2, f"expected the contrastive pair, got {len(examples)}"

    planner_alone = [e for e in examples if "local tips" not in e]
    with_tips = [e for e in examples if "local tips" in e]
    assert len(planner_alone) == 1, "the planner-alone half of the pair is gone"
    assert len(with_tips) == 1, "the local-tips half of the pair is gone"

    assert "`plan=[]`" in planner_alone[0]
    assert '`plan=["concierge"]`' in with_tips[0]


def test_plan_field_description_carries_the_carve_out():
    # The model reads the schema description independently of the prompt
    # (the #156 lesson); in v11 only the prompt carried the exception.
    description = SupervisorIntent.model_fields["plan"].description
    assert description is not None
    normalized = " ".join(description.split())
    assert "never omit a step the primary has NO tool for" in normalized
    assert "concierge-only" in normalized
    assert "Weather and places are planner-owned" in normalized
