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

import pytest
from app.agents.supervisor import SupervisorIntent, make_supervisor
from app.prompts.registry import registry
from langchain_core.messages import HumanMessage

# None = the active version; 13 = the gh-148 version, pinned explicitly until
# active.yaml is bumped so the v12 contracts are proven on v13 too.
_VERSIONS = [None, 13]


def _raw(version: int | None = None) -> str:
    return registry.get("supervisor", version=version)


def _normalized(version: int | None = None) -> str:
    return " ".join(_raw(version).split())


@pytest.mark.parametrize("version", _VERSIONS)
def test_supervisor_prompt_names_concierge_only_tools(version):
    # The fan-out trigger is a tool list the model can check, not a judgment
    # call. All three tools are concierge-only in app/tools/registry.py.
    text = _normalized(version)
    for tool in ("get_local_tips", "get_visa", "search_travel_knowledge"):
        assert tool in text, f"supervisor prompt no longer names {tool}"


@pytest.mark.parametrize("version", _VERSIONS)
def test_supervisor_prompt_keeps_planner_owned_not_a_trigger(version):
    # The #149 guard: weather and places are planner-owned, so they must NOT
    # read as a reason to add a second worker. Asserted on substance, not on a
    # verbatim sentence — a reword that keeps the rule must keep passing.
    text = _normalized(version)
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
        "weather" in clause.lower() or "places" in clause.lower() for clause in denials
    ), "the fan-out denial is no longer tied to weather/places (the #149 guard)"


@pytest.mark.parametrize("version", _VERSIONS)
def test_supervisor_prompt_has_contrastive_pair(version):
    # The teaching signal is the CONTRAST: the same request with and without
    # local tips, adjacent in the few-shot block. A lone fan-out example would
    # only raise fan-out pressure (the #149 risk).
    examples = [
        line
        for line in _raw(version).splitlines()
        if line.startswith('- "plan my weekend')
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


# --- gh-148 (v13): explicit language switch, #149/#150/#151 routing examples ---


def _example(text: str, phrase: str) -> str:
    lines = [line for line in text.splitlines() if phrase in line]
    assert len(lines) == 1, f"expected one example line for {phrase!r}, got {lines}"
    return lines[0]


def test_v13_explicit_switch_rule_wins_immediately_and_sticks():
    # #148: an explicit request to reply in a language wins at once, even when
    # the request itself is written in another language, and stays sticky.
    text = _normalized(13)
    assert "explicit request to reply in a language" in text
    assert "Trả lời bằng tiếng Anh được không?" in text
    assert "whatever language the request itself is written in" in text
    assert "sticky" in text
    # Loanword/interjection noise still never switches.
    assert "'ok','fine','good','sure'" in text


def test_v13_explicit_switch_negative_question_about_a_language():
    # A question ABOUT a language is not a request to reply in it.
    line = _example(_raw(13), "How do you say 'thank you' in English?")
    assert "❌" in line
    assert "established language" in line


def test_language_field_description_explicit_switch():
    description = SupervisorIntent.model_fields["language"].description
    assert description is not None
    normalized = " ".join(description.split())
    assert "explicitly asks to reply in a language" in normalized
    assert "even if that request is written in another language" in normalized
    assert "question ABOUT a language" in normalized
    # The noise guard is kept.
    assert "'ok','fine','good'" in normalized


def test_established_language_hint_explicit_switch():
    seen: list = []

    class _Router:
        def with_structured_output(self, *_a, **_k):
            return self

        def invoke(self, messages):
            seen.extend(messages)
            return SupervisorIntent(target_agent="concierge", language="en")

    node = make_supervisor(_Router())
    node(
        {
            "messages": [HumanMessage("Trả lời bằng tiếng Anh được không?")],
            "language": "vi",
        },
        None,
    )
    system_text = " ".join(str(m.content) for m in seen if m.type == "system")
    assert "Established conversation language: vi" in system_text
    assert "or explicitly asks for another language" in system_text


def test_v13_journal_never_adds_itinerary_items():
    # #150: adding an item to a day is a planner edit, not a journal note.
    text = _normalized(13)
    assert "never adds or moves itinerary items" in text
    line = _example(_raw(13), "Thêm buổi tối ăn lẩu vào ngày 2 nhé")
    assert "**planner**" in line


def test_v13_budget_vs_general_cost_knowledge_contrastive_pair():
    # #151: budget is THIS trip's numbers; general cost knowledge is concierge.
    raw = _raw(13)
    general = _example(
        raw, "Break down a typical daily budget for backpacking in Vietnam"
    )
    mine = _example(raw, "Set a simple budget for my trip")
    assert "**concierge**" in general
    assert "**budget**" in mine
    lines = raw.splitlines()
    assert abs(lines.index(general) - lines.index(mine)) == 1, "pair must be adjacent"


def test_v13_flights_plus_weather_is_one_planner_job():
    # #149: the literal example — weather is planner-owned, no fan-out.
    line = _example(_raw(13), "Find flights to Tokyo and tell me the weather there")
    assert "**planner**" in line
    assert "`plan=[]`" in line
