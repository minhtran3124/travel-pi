"""Typed agent SSE event taxonomy.

Every emission on ``/agent/stream`` is a named JSON event. Each factory returns
a :class:`~app.core.streaming.TypedSSEEvent` whose ``data`` is a compact JSON
string, so the frontend parses one shape regardless of channel (tokens
included — JSON escapes newlines, so no per-line markdown splitting is needed).

Wire shape: ``event: <name>\\ndata: <json>\\n\\n``.

Taxonomy
--------
* ``start``       — stream opened: ``{conversation_id}``
* ``token``       — assistant text delta: ``{content}``
* ``reset``       — discard the superseded draft (reflection revision): ``{}``
* ``subagent``    — active specialist changed: ``{name}``
* ``tool_call``   — a tool invocation started: ``{id, name, args_preview, subagent}``
* ``tool_result`` — a tool finished: ``{id, status}`` (``status`` ∈ ``ok|error``)
* ``interrupt``   — HITL plan-approval pending: ``{conversation_id, payload}``
* ``done``        — terminal success: ``{conversation_id, current_flow}``
* ``error``       — terminal failure: ``{code, message}``
"""

from __future__ import annotations

import json
from typing import Any

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


def interrupt(*, conversation_id: str, payload: Any) -> TypedSSEEvent:
    return _event("interrupt", {"conversation_id": conversation_id, "payload": payload})


def done(*, conversation_id: str, current_flow: str | None) -> TypedSSEEvent:
    return _event(
        "done", {"conversation_id": conversation_id, "current_flow": current_flow}
    )


def error(*, code: str, message: str) -> TypedSSEEvent:
    return _event("error", {"code": code, "message": message})
