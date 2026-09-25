"""Traveller personas: generation, persistence, and the per-turn prompt.

`generate` runs one `claude_cli.run` with a list schema and writes
`personas.json`; `load` reads it back; `traveller_system_prompt` renders the
tau-bench user-simulator rules with a persona card (design §5.2).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from sim.claude_cli import DriverError, run

_PROMPTS = Path(__file__).parent / "prompts"
_RUNS = Path(__file__).parent / "runs"

Style = Literal["terse", "chatty", "changes_mind", "impatient"]


class Budget(BaseModel):
    amount: float
    currency: str


class TripGoal(BaseModel):
    destination: str
    date_window: str | None = None
    party_size: int
    interests: list[str] = Field(default_factory=list)


class Persona(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]+$")
    name: str
    home_city: str | None = None
    country_code: str | None = None
    language: str
    budget: Budget
    trip_goal: TripGoal
    style: Style
    will_book: bool
    max_turns: int = Field(ge=4, le=8)


def _list_schema() -> dict:
    # Hoist `$defs` to the document root so the nested `$ref`s (which point at
    # `#/$defs/X`) resolve; leaving them under `properties.personas.items` would
    # leave every ref dangling.
    item = Persona.model_json_schema()
    defs = item.pop("$defs", None)
    schema = {
        "type": "object",
        "properties": {
            "personas": {
                "type": "array",
                "items": item,
            }
        },
        "required": ["personas"],
    }
    if defs:
        schema["$defs"] = defs
    return schema


_LIST_SCHEMA = _list_schema()


def _read(name: str) -> str:
    return (_PROMPTS / name).read_text(encoding="utf-8")


def _default_run_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    return _RUNS / f"{stamp}-{uuid4().hex[:6]}"


async def generate(
    n: int,
    seed: int | None = None,
    out_dir: Path | str | None = None,
) -> list[Persona]:
    output = await run(
        system_prompt=_read("persona_generator.md"),
        user_prompt=f"Generate {n} varied travellers. seed={seed}.",
        schema=_LIST_SCHEMA,
    )
    raw = output.get("personas")
    if not isinstance(raw, list):
        raise DriverError("persona generation returned no personas array")
    personas = [Persona.model_validate(item) for item in raw]

    ids = [p.id for p in personas]
    if len(set(ids)) != len(ids):
        raise DriverError("persona generation produced duplicate ids")

    target = Path(out_dir) if out_dir is not None else _default_run_dir()
    target.mkdir(parents=True, exist_ok=True)
    payload = [p.model_dump() for p in personas]
    (target / "personas.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return personas


def load(path: Path | str) -> list[Persona]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise DriverError("personas.json must hold a JSON array of personas")
    return [Persona.model_validate(item) for item in data]


def _persona_card(persona: Persona) -> str:
    goal = persona.trip_goal
    origin = (
        f"{persona.home_city}, {persona.country_code}"
        if persona.home_city
        else "unknown (you have not settled on a departure point)"
    )
    dates = goal.date_window or "unknown (you have not fixed the dates)"
    interests = ", ".join(goal.interests) or "open to suggestions"
    return "\n".join(
        [
            f"- Name: {persona.name}",
            f"- Home / origin: {origin}",
            f"- Language: {persona.language}",
            f"- Budget: {persona.budget.amount:g} {persona.budget.currency}",
            f"- Destination: {goal.destination}",
            f"- Dates: {dates}",
            f"- Party size: {goal.party_size}",
            f"- Interests: {interests}",
            f"- Style: {persona.style}",
            f"- Willing to book: {'yes' if persona.will_book else 'no'}",
        ]
    )


def traveller_system_prompt(persona: Persona) -> str:
    template = _read("traveller.md")
    return (
        template.replace("{{PERSONA_CARD}}", _persona_card(persona))
        .replace("{{LANGUAGE}}", persona.language)
        .replace("{{STYLE}}", persona.style)
    )
