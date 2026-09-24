"""Every research model call knows the traveller's language (research-dossier-reader SC-3).

Run ``0f71586a`` wrote its summary in Vietnamese but every dimension file in English: the
``Language:`` line sits in the main agent's message, and a subagent only gets the task
text the main agent chose to write. ``_WriteInTravellerLanguage`` puts the language into
each model call's system message from ``state["language"]``.
"""

from __future__ import annotations

import asyncio

import pytest
from app.clients.llm import FakeLLM
from app.research.agent import _subagents, _WriteInTravellerLanguage
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import SystemMessage


def _request(language: str | None) -> ModelRequest:
    state = {"messages": []}
    if language is not None:
        state["language"] = language
    return ModelRequest(
        model=FakeLLM(responses=[]),
        messages=[],
        system_message=SystemMessage(content="You research flights."),
        state=state,
    )


def _seen_system(middleware, request) -> str:
    seen: list[str] = []

    def handler(req):
        seen.append(req.system_message.content)
        return "ok"

    middleware.wrap_model_call(request, handler)
    return seen[0]


@pytest.mark.parametrize(
    ("language", "name"), [("vi", "Vietnamese"), ("en", "English")]
)
def test_the_system_message_names_the_language(language, name) -> None:
    text = _seen_system(_WriteInTravellerLanguage(), _request(language))

    assert text.startswith("You research flights.")
    assert f"in {name}" in text


def test_no_language_in_state_leaves_the_request_alone() -> None:
    request = _request(None)
    assert _seen_system(_WriteInTravellerLanguage(), request) == "You research flights."


def test_async_path_names_the_language_too() -> None:
    seen: list[str] = []

    async def handler(req):
        seen.append(req.system_message.content)
        return "ok"

    asyncio.run(_WriteInTravellerLanguage().awrap_model_call(_request("vi"), handler))
    assert "in Vietnamese" in seen[0]


def test_every_subagent_binds_the_language_middleware() -> None:
    for spec in _subagents():
        assert any(
            isinstance(m, _WriteInTravellerLanguage) for m in spec["middleware"]
        ), spec["name"]
