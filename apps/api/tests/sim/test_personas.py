"""SC-6 — the persona generator, exercised through the fake ``claude``.

The fake runs in ``ok`` mode and returns a fixture structured output listing
three personas. The suite stays fully offline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sim import personas

FAKE = Path(__file__).parent / "fixtures" / "fake_claude.py"

THREE_PERSONAS = {
    "personas": [
        {
            "id": "mai-hanoi",
            "name": "Mai",
            "home_city": "Hanoi",
            "country_code": "VN",
            "language": "vi",
            "budget": {"amount": 1500, "currency": "USD"},
            "trip_goal": {
                "destination": "Da Nang",
                "date_window": "early May 2026",
                "party_size": 2,
                "interests": ["beaches", "food"],
            },
            "style": "chatty",
            "will_book": True,
            "max_turns": 6,
        },
        {
            "id": "sam-london",
            "name": "Sam",
            "home_city": "London",
            "country_code": "GB",
            "language": "en",
            "budget": {"amount": 2000, "currency": "GBP"},
            "trip_goal": {
                "destination": "Tokyo",
                "date_window": None,
                "party_size": 1,
                "interests": ["temples"],
            },
            "style": "terse",
            "will_book": False,
            "max_turns": 4,
        },
        {
            "id": "lea-paris",
            "name": "Lea",
            "home_city": None,
            "country_code": None,
            "language": "fr",
            "budget": {"amount": 3000, "currency": "EUR"},
            "trip_goal": {
                "destination": "Rome",
                "date_window": "sometime in autumn",
                "party_size": 3,
                "interests": ["museums", "wine"],
            },
            "style": "changes_mind",
            "will_book": True,
            "max_turns": 8,
        },
    ]
}


@pytest.fixture()
def fake_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SIM_CLAUDE_BIN", str(FAKE))
    argv_file = tmp_path / "argv.json"
    output_file = tmp_path / "personas_out.json"
    output_file.write_text(json.dumps(THREE_PERSONAS), encoding="utf-8")
    monkeypatch.setenv("FAKE_CLAUDE_ARGV_FILE", str(argv_file))
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUT_FILE", str(output_file))
    monkeypatch.delenv("FAKE_CLAUDE_MODE", raising=False)
    return {"argv": argv_file, "tmp": tmp_path}


@pytest.mark.asyncio
async def test_generate_returns_three_personas_and_writes_file(fake_env):
    out_dir = fake_env["tmp"] / "run"
    result = await personas.generate(3, seed=1, out_dir=out_dir)
    assert len(result) == 3
    assert all(isinstance(p, personas.Persona) for p in result)
    assert (out_dir / "personas.json").is_file()


@pytest.mark.asyncio
async def test_argv_holds_the_json_schema_flag(fake_env):
    await personas.generate(3, seed=1, out_dir=fake_env["tmp"] / "run")
    argv = json.loads(fake_env["argv"].read_text())
    assert "--json-schema" in argv


@pytest.mark.asyncio
async def test_load_round_trips_the_written_cast(fake_env):
    out_dir = fake_env["tmp"] / "run"
    result = await personas.generate(3, seed=1, out_dir=out_dir)
    assert personas.load(out_dir / "personas.json") == result


@pytest.mark.asyncio
async def test_generate_rejects_duplicate_ids(fake_env, monkeypatch):
    dup = {"personas": [THREE_PERSONAS["personas"][0]] * 2}
    out = fake_env["tmp"] / "dup.json"
    out.write_text(json.dumps(dup), encoding="utf-8")
    monkeypatch.setenv("FAKE_CLAUDE_OUTPUT_FILE", str(out))
    with pytest.raises(personas.DriverError):
        await personas.generate(2, seed=1, out_dir=fake_env["tmp"] / "run")


def test_load_rejects_non_list_payload(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"personas": []}), encoding="utf-8")
    with pytest.raises(personas.DriverError):
        personas.load(bad)


def _collect_refs(node):
    refs = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                refs.append(value)
            else:
                refs.extend(_collect_refs(value))
    elif isinstance(node, list):
        for item in node:
            refs.extend(_collect_refs(item))
    return refs


def test_list_schema_refs_resolve_at_document_root():
    schema = personas._LIST_SCHEMA
    refs = _collect_refs(schema)
    assert refs, "expected the persona schema to use $ref for nested models"
    defs = schema.get("$defs", {})
    for ref in refs:
        assert ref.startswith("#/$defs/")
        assert ref.split("/", 2)[2] in defs


def test_persona_rejects_bad_slug_and_out_of_range_turns():
    base = THREE_PERSONAS["personas"][0]
    with pytest.raises(ValueError):
        personas.Persona.model_validate({**base, "id": "Not A Slug"})
    with pytest.raises(ValueError):
        personas.Persona.model_validate({**base, "max_turns": 9})


def test_traveller_system_prompt_carries_card_and_taubench_rules():
    persona = personas.Persona.model_validate(THREE_PERSONAS["personas"][0])
    prompt = personas.traveller_system_prompt(persona)
    assert "Mai" in prompt
    assert "Da Nang" in prompt
    assert "- Language: vi" in prompt
    assert "{{" not in prompt
    assert "intent_done" in prompt
    assert "one message per turn" in prompt


def test_load_rejects_duplicate_ids(tmp_path):
    dup = [THREE_PERSONAS["personas"][0], THREE_PERSONAS["personas"][0]]
    bad = tmp_path / "dup.json"
    bad.write_text(json.dumps(dup), encoding="utf-8")
    with pytest.raises(personas.DriverError):
        personas.load(bad)


def test_persona_card_renders_contact_details():
    payload = {
        **THREE_PERSONAS["personas"][0],
        "email": "mai@example.com",
        "phone": "+1-555-0100",
    }
    persona = personas.Persona.model_validate(payload)
    card = personas.traveller_system_prompt(persona)
    assert "mai@example.com" in card
    assert "+1-555-0100" in card


def test_old_payload_without_contact_loads_and_card_notes_absence(tmp_path):
    # THREE_PERSONAS predate the email/phone fields — they must still load.
    old = tmp_path / "old.json"
    old.write_text(json.dumps(THREE_PERSONAS["personas"]), encoding="utf-8")
    loaded = personas.load(old)
    assert loaded[0].email is None
    assert loaded[0].phone is None
    card = personas.traveller_system_prompt(loaded[0])
    assert "no contact details on file" in card
