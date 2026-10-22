"""Typed agent SSE event taxonomy.

Each factory returns a compact-JSON ``TypedSSEEvent`` on the wire shape
``event: <name>\\ndata: <json>\\n\\n``. ``done``'s ``assistant_message_id`` /
``agent_run_id`` are filled in by ``persist_assistant_turn`` once the reply row
is committed, so ``done`` means the answer is durable.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.languages import DEFAULT_LANGUAGE
from app.core.streaming import TypedSSEEvent

#: Max length of the JSON-serialised tool args echoed to the client.
ARGS_PREVIEW_LIMIT = 200


def _event(name: str, payload: dict[str, Any]) -> TypedSSEEvent:
    return TypedSSEEvent(event=name, data=json.dumps(payload, separators=(",", ":")))


def start(conversation_id: str) -> TypedSSEEvent:
    return _event("start", {"conversation_id": conversation_id})


def token(content: str) -> TypedSSEEvent:
    return _event("token", {"content": content})


def reset() -> TypedSSEEvent:
    return _event("reset", {})


def subagent(name: str) -> TypedSSEEvent:
    return _event("subagent", {"name": name})


def tool_call(*, id: str, name: str, args: Any, subagent: str | None) -> TypedSSEEvent:
    preview = json.dumps(args, separators=(",", ":"), default=str)
    if len(preview) > ARGS_PREVIEW_LIMIT:
        preview = preview[:ARGS_PREVIEW_LIMIT] + "…"
    return _event(
        "tool_call",
        {"id": id, "name": name, "args_preview": preview, "subagent": subagent},
    )


def tool_result(*, id: str, status: str) -> TypedSSEEvent:
    return _event("tool_result", {"id": id, "status": status})


def panel(
    *, tool_call_id: str, kind: str, data: Any, language: str = DEFAULT_LANGUAGE
) -> TypedSSEEvent:
    return _event(
        "panel",
        {
            "tool_call_id": tool_call_id,
            "kind": kind,
            "data": data,
            "language": language,
        },
    )


def interrupt(*, conversation_id: str, payload: Any) -> TypedSSEEvent:
    return _event("interrupt", {"conversation_id": conversation_id, "payload": payload})


def done(
    *,
    conversation_id: str,
    current_flow: str | None,
    suggestions: list[str],
    language: str = DEFAULT_LANGUAGE,
    trip_id: str | None = None,
    usage: dict | None = None,
    assistant_message_id: str | None = None,
    agent_run_id: str | None = None,
) -> TypedSSEEvent:
    return _event(
        "done",
        {
            "conversation_id": conversation_id,
            "assistant_message_id": assistant_message_id,
            "agent_run_id": agent_run_id,
            "current_flow": current_flow,
            "suggestions": suggestions,
            "language": language,
            "trip_id": trip_id,
            "usage": usage,
        },
    )


def error(*, code: str, message: str) -> TypedSSEEvent:
    return _event("error", {"code": code, "message": message})
