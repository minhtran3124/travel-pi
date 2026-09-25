"""SSE stream client for the ``/agent/stream`` endpoint.

Parses the typed event stream defined in ``app/streaming/events.py`` and maps it
to the lobby UI event types from design §5.7. The bus stamps ``t`` on each UI
event; the mapper only supplies ``type``, ``persona_id``, and payload fields.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterable, Iterator
from dataclasses import dataclass

import httpx


class HttpStatusError(Exception):
    """Raised when ``/agent/stream`` answers with a non-200 status."""

    def __init__(
        self,
        status: int,
    ) -> None:
        super().__init__(f"unexpected status {status}")
        self.status = status


@dataclass
class SseEvent:
    """One named Server-Sent Event with its decoded JSON payload."""

    name: str
    data: dict


class _Accumulator:
    """Line-oriented SSE decoder, shared by ``parse`` and ``stream_turn``."""

    def __init__(self) -> None:
        self._name: str | None = None
        self._data: list[str] = []

    def feed(
        self,
        line: str,
    ) -> SseEvent | None:
        line = line.rstrip("\r")
        if line == "":
            return self._flush()
        if line.startswith(":"):
            return None
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "event":
            self._name = value
        elif field == "data":
            self._data.append(value)
        return None

    def flush(self) -> SseEvent | None:
        return self._flush()

    def _flush(self) -> SseEvent | None:
        if self._name is None:
            self._data = []
            return None
        payload = "\n".join(self._data)
        event = SseEvent(self._name, json.loads(payload) if payload else {})
        self._name = None
        self._data = []
        return event


def parse(lines: Iterable[str]) -> Iterator[SseEvent]:
    """Decode an iterable of raw SSE lines into ``SseEvent`` values."""
    acc = _Accumulator()
    for line in lines:
        event = acc.feed(line)
        if event is not None:
            yield event
    tail = acc.flush()
    if tail is not None:
        yield tail


async def stream_turn(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    body: dict,
) -> AsyncIterator[SseEvent]:
    """POST one turn to ``/agent/stream`` and yield its SSE events.

    Raises ``HttpStatusError`` when the response status is not 200.
    """
    async with client.stream(
        "POST",
        f"{base_url}/agent/stream",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    ) as response:
        if response.status_code != 200:
            await response.aread()
            raise HttpStatusError(response.status_code)
        acc = _Accumulator()
        async for line in response.aiter_lines():
            event = acc.feed(line)
            if event is not None:
                yield event
        tail = acc.flush()
        if tail is not None:
            yield tail


def to_ui_events(
    persona_id: str,
    ev: SseEvent,
) -> list[dict]:
    """Map one SSE event to zero or more UI events (design §5.7).

    ``start``, ``panel``, and ``reset`` carry no lobby animation, so they map to
    nothing. ``bot_done.reply`` is filled by the caller that accumulates tokens.
    """
    data = ev.data
    if ev.name == "subagent":
        return [
            {"type": "bot_subagent", "persona_id": persona_id, "name": data.get("name")}
        ]
    if ev.name == "tool_call":
        return [
            {
                "type": "bot_tool",
                "persona_id": persona_id,
                "name": data.get("name"),
                "status": "running",
            }
        ]
    if ev.name == "tool_result":
        return [
            {"type": "bot_tool", "persona_id": persona_id, "status": data.get("status")}
        ]
    if ev.name == "token":
        return [
            {
                "type": "bot_token",
                "persona_id": persona_id,
                "text": data.get("content", ""),
            }
        ]
    if ev.name == "interrupt":
        payload = data.get("payload") or {}
        return [
            {
                "type": "bot_interrupt",
                "persona_id": persona_id,
                "kind": payload.get("type"),
            }
        ]
    if ev.name == "done":
        return [
            {"type": "bot_done", "persona_id": persona_id, "usage": data.get("usage")}
        ]
    if ev.name == "error":
        return [
            {
                "type": "bot_error",
                "persona_id": persona_id,
                "code": data.get("code"),
                "message": data.get("message"),
            }
        ]
    return []
