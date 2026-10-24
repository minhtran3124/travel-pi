"""Typed research-progress SSE event taxonomy (sibling of ``events.py``).

Each event serialises to the same wire shape the chat taxonomy uses via
``sse_response``: ``event: <name>\\ndata: <compact-json>\\n\\n``. Payloads carry
projected progress only — never message text, tool arguments or dossier content
(design §4): ``research_tool``/``research_file`` expose a tool ``name``/``status``
and a file ``path``/``bytes``, not ``args`` or ``content``.

``derive_events`` is a table-driven mapper from one ``astream_events(version="v3")``
item (or a rubric ``on_evaluation`` payload) to zero or more events, so adjusting a
fixture shape never touches callers (design §5); an unrecognised shape maps to
``[]`` and never raises.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from app.core.streaming import TypedSSEEvent


@dataclass(frozen=True)
class ResearchEvent:
    EVENT: ClassVar[str] = "research"

    def _payload(self) -> dict[str, Any]:
        return {}

    def to_sse(self) -> TypedSSEEvent:
        return TypedSSEEvent(
            event=self.EVENT,
            data=json.dumps(self._payload(), separators=(",", ":")),
        )


@dataclass(frozen=True)
class ResearchStart(ResearchEvent):
    EVENT = "research_start"
    run_id: str
    trip_id: str

    def _payload(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "trip_id": self.trip_id}


@dataclass(frozen=True)
class ResearchPhase(ResearchEvent):
    EVENT = "research_phase"
    todos: list[dict[str, str]]

    def _payload(self) -> dict[str, Any]:
        return {"todos": self.todos}


@dataclass(frozen=True)
class ResearchSubagent(ResearchEvent):
    EVENT = "research_subagent"
    name: str
    status: str

    def _payload(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status}


@dataclass(frozen=True)
class ResearchTool(ResearchEvent):
    EVENT = "research_tool"
    name: str
    status: str

    def _payload(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status}


@dataclass(frozen=True)
class ResearchFile(ResearchEvent):
    EVENT = "research_file"
    path: str
    bytes: int

    def _payload(self) -> dict[str, Any]:
        return {"path": self.path, "bytes": self.bytes}


@dataclass(frozen=True)
class ResearchEval(ResearchEvent):
    EVENT = "research_eval"
    iteration: int
    result: str
    explanation: str

    def _payload(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "result": self.result,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class ResearchDone(ResearchEvent):
    EVENT = "research_done"
    status: str
    files: list[str]
    proposal_ready: bool

    def _payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "files": self.files,
            "proposal_ready": self.proposal_ready,
        }


@dataclass(frozen=True)
class ResearchError(ResearchEvent):
    EVENT = "research_error"
    code: str
    message: str

    def _payload(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message}


#: Write tools whose invocation yields a file event — path only, never content.
_WRITE_TOOLS = {"write_file", "edit_file"}
_TOOL_STATUS = {"on_tool_start": "start", "on_tool_end": "end"}


def _file_meta(event: dict) -> tuple[str | None, int]:
    data = event.get("data") or {}
    inp = data.get("input") or {}
    path = inp.get("file_path") or inp.get("path")
    content = inp.get("content") or inp.get("new_string") or ""
    size = len(content.encode("utf-8")) if isinstance(content, str) else 0
    return path, size


def _tool(event: dict) -> list[ResearchEvent]:
    name = event.get("name")
    if not name:
        return []
    status = _TOOL_STATUS[event["event"]]
    out: list[ResearchEvent] = [ResearchTool(name=name, status=status)]
    if name in _WRITE_TOOLS:
        path, size = _file_meta(event)
        if path:
            out.append(ResearchFile(path=path, bytes=size))
    return out


def _subagent(data: dict) -> list[ResearchEvent]:
    name = data.get("name")
    if not name:
        return []
    return [ResearchSubagent(name=name, status=data.get("status", ""))]


def _phase(data: dict) -> list[ResearchEvent]:
    todos = data.get("todos")
    if not isinstance(todos, list):
        return []
    cleaned = [
        {"content": t.get("content", ""), "status": t.get("status", "")}
        for t in todos
        if isinstance(t, dict)
    ]
    return [ResearchPhase(todos=cleaned)]


def _eval(data: dict) -> list[ResearchEvent]:
    if "result" not in data and "iteration" not in data:
        return []
    return [
        ResearchEval(
            iteration=data.get("iteration", 0),
            result=data.get("result", ""),
            explanation=data.get("explanation", ""),
        )
    ]


_CUSTOM: dict[str, Callable[[dict], list[ResearchEvent]]] = {
    "subagent": _subagent,
    "phase": _phase,
    "todos": _phase,
    "evaluation": _eval,
}


def _custom(event: dict) -> list[ResearchEvent]:
    builder = _CUSTOM.get(event.get("name", ""))
    return builder(event.get("data") or {}) if builder else []


_HANDLERS: dict[str, Callable[[dict], list[ResearchEvent]]] = {
    "on_tool_start": _tool,
    "on_tool_end": _tool,
    "on_custom_event": _custom,
    "on_evaluation": lambda e: _eval(e.get("data") or e),
}


#: tool_call_id -> tool name, remembered from ``tool-started`` because v3's
#: ``tool-finished`` carries only the id. Popped on finish; bounded so a run whose
#: tools never finish cannot grow it without limit.
_V3_TOOL_NAMES: dict[str, str] = {}
_V3_TOOL_NAMES_MAX = 512


def _v3_tools(data: dict) -> list[ResearchEvent]:
    kind = data.get("event")
    call_id = data.get("tool_call_id")
    if kind == "tool-started":
        name = data.get("tool_name")
        if not name:
            return []
        if call_id:
            if len(_V3_TOOL_NAMES) >= _V3_TOOL_NAMES_MAX:
                _V3_TOOL_NAMES.pop(next(iter(_V3_TOOL_NAMES)))
            _V3_TOOL_NAMES[call_id] = name
        return _tool({"event": "on_tool_start", "name": name, "data": data})
    if kind in ("tool-finished", "tool-error"):
        name = _V3_TOOL_NAMES.pop(call_id, None) if call_id else None
        return [ResearchTool(name=name, status="end")] if name else []
    return []


def _v3_values(data: object) -> list[ResearchEvent]:
    return _phase(data) if isinstance(data, dict) and "todos" in data else []


def _v3(event: dict) -> list[ResearchEvent]:
    """Map one ``astream_events(version="v3")`` protocol event (``{"type": "event",
    "method": ..., "params": {"data": ...}}``) onto progress events."""
    method = event.get("method")
    data = (event.get("params") or {}).get("data")
    if method == "tools" and isinstance(data, dict):
        return _v3_tools(data)
    if method == "values":
        return _v3_values(data)
    return []


def derive_events(event: dict) -> list[ResearchEvent]:
    try:
        if event.get("type") == "event" and "method" in event:
            return _v3(event)
        kind = event.get("event")
        if kind is None:
            return _eval(event)
        handler = _HANDLERS.get(kind)
        return handler(event) if handler else []
    except Exception:
        return []
